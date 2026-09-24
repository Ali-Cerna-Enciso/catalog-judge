"""Prepara fixtures derivados de datasets públicos, sin copiar los raw al repo.

Retail se agrega en chunks; tickets se selecciona y cura en español. El script
requiere que los raw temporales ya estén descargados, o puede descargarlos a
un directorio temporal explícito. No envía datos a ningún servicio.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import tempfile
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_DIR = Path(
    os.environ.get("CATALOG_JUDGE_PUBLIC_TMP", str(Path(tempfile.gettempdir()) / "catalog-judge-public"))
)
RETAIL_URL = "https://huggingface.co/datasets/t4tiana/store-sales-time-series-forecasting/resolve/main/train.csv"
TICKETS_URL = "https://huggingface.co/datasets/Tobi-Bueck/customer-support-tickets/resolve/main/dataset-tickets-multi-lang-4-20k.csv"
TICKET_DATASET = "Tobi-Bueck/customer-support-tickets"
RETAIL_DATASET = "t4tiana/store-sales-time-series-forecasting"
FEATURE_VERSION = "favorita-demand-features-v2"
TICKET_CURATION_VERSION = "tickets-public-curation-v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"download {target.name}", flush=True)
    request = urllib.request.Request(url, headers={"User-Agent": "catalog-judge-public-fixture/0.2"})
    with urllib.request.urlopen(request, timeout=180) as response, target.open("wb") as handle:
        while chunk := response.read(1024 * 1024):
            handle.write(chunk)


def ensure_raw(raw_dir: Path, retail: Path | None, tickets: Path | None) -> tuple[Path, Path]:
    retail_path = retail or raw_dir / "retail.csv"
    tickets_path = tickets or raw_dir / "tickets.csv"
    if not retail_path.exists():
        download(RETAIL_URL, retail_path)
    if not tickets_path.exists():
        download(TICKETS_URL, tickets_path)
    return retail_path, tickets_path


def aggregate_retail(raw_path: Path) -> tuple[list[dict[str, Any]], date, date]:
    """Aggregate the public Favorita family-by-store demand series.

    The public mirror has no product master or stock field.  A row is therefore
    a transparent ``store_nbr × family`` series, not a fabricated SKU.
    """

    columns = ["date", "store_nbr", "family", "sales", "onpromotion"]
    max_date: pd.Timestamp | None = None
    for chunk in pd.read_csv(raw_path, usecols=columns, chunksize=200_000, low_memory=False):
        value = pd.to_datetime(chunk["date"], errors="coerce").max()
        if pd.notna(value):
            max_date = value if max_date is None or value > max_date else max_date
    if max_date is None:
        raise ValueError("el retail raw no contiene fechas válidas")
    recent_start = max_date - pd.Timedelta(days=27)
    previous_start = max_date - pd.Timedelta(days=55)
    aggregates: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "n": 0, "sum": 0.0, "sumsq": 0.0, "positive": 0, "promo": 0,
        "recent_n": 0, "recent_sum": 0.0, "previous_n": 0, "previous_sum": 0.0,
        "store_nbr": 0, "family": "",
    })
    for chunk in pd.read_csv(raw_path, usecols=columns, chunksize=200_000, low_memory=False):
        chunk["date"] = pd.to_datetime(chunk["date"], errors="coerce")
        chunk["sales"] = pd.to_numeric(chunk["sales"], errors="coerce")
        chunk["onpromotion"] = pd.to_numeric(chunk["onpromotion"], errors="coerce").fillna(0)
        for row in chunk.itertuples(index=False):
            if pd.isna(row.store_nbr) or pd.isna(row.date) or pd.isna(row.sales) or pd.isna(row.family):
                continue
            store = int(row.store_nbr)
            family = str(row.family).strip()
            series_id = f"store_{store:02d}__{family}"
            value = float(row.sales)
            data = aggregates[series_id]
            data["store_nbr"] = store
            data["family"] = family
            data["n"] += 1
            data["sum"] += value
            data["sumsq"] += value * value
            data["positive"] += int(value > 0)
            data["promo"] += int(row.onpromotion > 0)
            if row.date >= recent_start:
                data["recent_n"] += 1
                data["recent_sum"] += value
            elif row.date >= previous_start and row.date < recent_start:
                data["previous_n"] += 1
                data["previous_sum"] += value
    rows: list[dict[str, Any]] = []
    for series_id, data in aggregates.items():
        count = int(data["n"])
        mean = data["sum"] / count
        variance = max(0.0, data["sumsq"] / count - mean * mean)
        cv = math.sqrt(variance) / abs(mean) if mean else 0.0
        previous_mean = data["previous_sum"] / data["previous_n"] if data["previous_n"] else 0.0
        recent_mean = data["recent_sum"] / data["recent_n"] if data["recent_n"] else 0.0
        ratio = recent_mean / previous_mean if data["previous_n"] and abs(previous_mean) > 1e-9 else None
        rows.append({
            "series_id": series_id,
            "store_nbr": int(data["store_nbr"]),
            "family": str(data["family"]),
            "avg_sales": round(mean, 6),
            "sales_cv": round(cv, 6),
            "active_day_share": round(data["positive"] / count, 6),
            "promo_share": round(data["promo"] / count, 6),
            "recent_vs_previous_ratio": None if ratio is None else round(ratio, 6),
            "rows_used": count,
            "feature_window_start": previous_start.date().isoformat(),
            "feature_window_end": max_date.date().isoformat(),
        })
    return rows, previous_start.date(), max_date.date()


def policy_values(row: dict[str, Any]) -> dict[str, Any]:
    ratio = row["recent_vs_previous_ratio"]
    avg = float(row["avg_sales"])
    cv = float(row["sales_cv"])
    active = float(row["active_day_share"])
    promo = float(row["promo_share"])
    drop = bool(avg > 0 and ratio is not None and ratio < 0.75)
    candidate = bool(avg > 0 and ratio is not None and ratio >= 1.10 and active >= 0.35)
    risk = bool(cv >= 1.0 or active < 0.25 or promo >= 0.50)
    exception = bool(drop or cv >= 1.5 or active < 0.15)
    decision = "exclude" if avg <= 0 or active < 0.10 else "review" if drop or risk or exception else "include"
    return {
        "demand_drop_alert": drop,
        "replenishment_candidate": candidate,
        "policy_handling_risk": risk,
        "policy_exception_needed": exception,
        "expected_series_decision": decision,
        "expected_handling_risk": risk,
        "expected_exception_needed": exception,
        "expected_route": {"include": "accept", "review": "review", "exclude": "block"}[decision],
    }


def _retail_stratum(row: dict[str, Any]) -> str:
    ratio = float(row["recent_vs_previous_ratio"])
    if ratio < 0.75:
        return "declining"
    if ratio >= 1.10:
        return "growing"
    if float(row["promo_share"]) >= 0.50 or float(row["sales_cv"]) >= 1.0:
        return "promo_or_volatile"
    return "stable"


def select_retail(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Select a balanced public sample of store×family series.

    The public source has no product master, so the fixture takes at most 12
    series from each of the eight largest usable families and rotates through
    the four demand strata inside each family.  The holdout reserves up to
    five series per available stratum and then fills a fixed budget of 20.
    """

    usable = [row for row in rows if row["rows_used"] >= 20 and row["recent_vs_previous_ratio"] is not None]
    if not usable:
        raise ValueError("no hay items retail utilizables")

    pools: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in usable:
        pools[str(row["family"])].append(row)
    family_order = sorted(pools, key=lambda family: (-len(pools[family]), family))
    family_order = family_order[:8]
    if len(family_order) < 2:
        raise ValueError("el mirror no contiene familias suficientes para un fixture retail")

    allocations = {family: min(12, len(pools[family])) for family in family_order}
    total = sum(allocations.values())
    while total < 96:
        candidates = [family for family in family_order if allocations[family] < len(pools[family])]
        if not candidates:
            break
        family = max(candidates, key=lambda name: (len(pools[name]) - allocations[name], name))
        allocations[family] += 1
        total += 1

    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    strata_order = ("declining", "growing", "promo_or_volatile", "stable")
    for family in family_order:
        target = allocations[family]
        by_stratum: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in sorted(pools[family], key=lambda item: str(item["series_id"])):
            by_stratum[_retail_stratum(row)].append(row)
        family_selected: list[dict[str, Any]] = []
        while len(family_selected) < target:
            added = False
            for stratum in strata_order:
                for row in by_stratum[stratum]:
                    item_id = str(row["series_id"])
                    if item_id in seen:
                        continue
                    family_selected.append(row)
                    seen.add(item_id)
                    added = True
                    if len(family_selected) == target:
                        break
                if len(family_selected) == target:
                    break
            if not added:
                break
        selected.extend(family_selected)
        if len(selected) == 96:
            break

    for row in sorted(usable, key=lambda item: str(item["series_id"])):
        if len(selected) == 96:
            break
        item_id = str(row["series_id"])
        if item_id not in seen:
            selected.append(row)
            seen.add(item_id)
    if len(selected) != 96:
        raise ValueError(f"solo se pudieron seleccionar {len(selected)} series retail")

    strata: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in selected:
        row["_stratum"] = _retail_stratum(row)
        strata[row["_stratum"]].append(row)
    # El holdout se congela antes de cualquier live: hasta cinco filas por
    # estrato disponible y relleno determinista del presupuesto de 20.
    holdout_ids: set[str] = set()
    for stratum in strata_order:
        members = sorted(strata[stratum], key=lambda item: str(item["series_id"]))
        holdout_ids.update(str(item["series_id"]) for item in members[-5:])
    for row in sorted(selected, key=lambda item: str(item["series_id"]), reverse=True):
        if len(holdout_ids) >= 20:
            break
        holdout_ids.add(str(row["series_id"]))
    for row in selected:
        row["evaluation_split"] = "holdout" if str(row["series_id"]) in holdout_ids else "dev"

    # Intercala familia y estrato para que la demo inicial muestre variedad.
    by_family_stratum: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in selected:
        by_family_stratum[(str(row["family"]), str(row["_stratum"]))].append(row)
    for members in by_family_stratum.values():
        members.sort(key=lambda item: str(item["series_id"]))
    ordered: list[dict[str, Any]] = []
    for index in range(12):
        for family in family_order:
            for stratum in strata_order:
                members = by_family_stratum[(family, stratum)]
                if index < len(members):
                    ordered.append(members[index])
    ordered.extend(row for row in selected if row not in ordered)
    output: list[dict[str, Any]] = []
    for row in ordered[:96]:
        row.pop("_stratum", None)
        row.update(policy_values(row))
        row["source_dataset"] = RETAIL_DATASET
        row["feature_version"] = FEATURE_VERSION
        output.append(row)
    return output


def safe_ticket_filter(frame: pd.DataFrame) -> pd.DataFrame:
    pii = re.compile(r"(?:@|\+?\d[\d ()-]{7,}\d|\b\d{8,}\b|https?://|<\s*[^>]+\s*>|your\s+(?:name|email|address)|\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})", re.I)
    brands = re.compile(r"\b(western digital|norton|bitdefender|kaspersky|mcafee|dell|lenovo|hp|apple|google|amazon|paypal|bank|asana|magento|firebase|postgresql|mysql|excel|word|powerpoint|iphone|android|windows|linux|sap|salesforce|hubspot|shopify|quickbooks|zoom|slack)\b", re.I)
    frame = frame[frame["language"].astype(str).str.lower().eq("en")].copy()
    frame["subject"] = frame["subject"].fillna("").astype(str).str.strip()
    frame["body"] = frame["body"].fillna("").astype(str).str.strip()
    mask = ~frame[["subject", "body"]].apply(lambda col: col.str.contains(pii)).any(axis=1)
    mask &= ~frame[["subject", "body"]].apply(lambda col: col.str.contains(brands)).any(axis=1)
    frame = frame[mask]
    frame = frame[(frame.subject.str.len() >= 15) & (frame.body.str.len() >= 45)]
    return frame.drop_duplicates(["subject", "body"])


def build_tickets(raw_path: Path, curation_path: Path) -> list[dict[str, Any]]:
    source = pd.read_csv(raw_path, usecols=["subject", "body", "type", "queue", "priority", "language"])
    eligible = safe_ticket_filter(source)
    eligible["source_row"] = eligible.index + 2
    eligible["_order"] = eligible.apply(lambda row: hashlib.sha256((str(row.subject) + "|" + str(row.body)).encode("utf-8")).hexdigest(), axis=1)
    curation = json.loads(curation_path.read_text(encoding="utf-8"))
    groups = curation["groups"]
    output: list[dict[str, Any]] = []
    queues = sorted(eligible["queue"].dropna().unique())
    for round_index in range(10):
        for queue in queues:
            pool = eligible[eligible.queue == queue].sort_values(["_order", "subject"], kind="stable")
            if len(pool) < 10 or queue not in groups or len(groups[queue]) != 10:
                raise ValueError(f"no hay selección/curación suficiente para {queue}")
            source_row = pool.iloc[round_index]
            entry = groups[queue][round_index]
            subject = entry["subject_es"]
            body = entry["body_es"]
            output.append({
                "source_id": f"hf-row-{int(source_row.source_row):06d}",
                "source_dataset": TICKET_DATASET,
                "source_queue": str(source_row.queue),
                "source_type": str(source_row.type),
                "source_priority": str(source_row.priority),
                "subject_es": subject,
                "body_es": body,
                "texto": f"{subject}\n{body}",
                "expected_area": entry["expected_area"],
                "expected_intent": entry["expected_intent"],
                "expected_urgency": entry["expected_urgency"],
                "expected_human": entry["expected_human"],
                "expected_security_legal": entry["expected_security_legal"],
                "expected_refund": entry["expected_refund"],
                "expected_actionability": entry["expected_actionability"],
                "expected_technical_repro": entry["expected_technical_repro"],
                "expected_route": entry["expected_route"],
                "curation_note": "Traducción/adaptación manual al español; subject/body originales omitidos; gold rubricado con ticket-rubric-v1.",
                "evaluation_split": "holdout" if round_index >= 5 else "dev",
            })
    if len(output) != 100 or len({row["source_id"] for row in output}) != 100 or len({row["texto"] for row in output}) != 100:
        raise ValueError("la curación no produjo 100 filas únicas")
    return output


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "" if value is None else value for key, value in row.items()})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--retail-raw", type=Path, default=None)
    parser.add_argument("--tickets-raw", type=Path, default=None)
    parser.add_argument("--delete-raw", action="store_true", help="borra los raw sólo después de escribir fixtures")
    args = parser.parse_args()
    retail_raw, tickets_raw = ensure_raw(args.raw_dir, args.retail_raw, args.tickets_raw)
    retail_rows, start, end = aggregate_retail(retail_raw)
    selected_retail = select_retail(retail_rows)
    tickets = build_tickets(tickets_raw, ROOT / "tickets" / "data" / "curation_100.json")
    retail_out = ROOT / "retail" / "data" / "favorita_demand_96.csv"
    tickets_out = ROOT / "tickets" / "data" / "tickets_100.csv"
    write_csv(retail_out, selected_retail)
    write_csv(tickets_out, tickets)
    policy_path = ROOT / "retail" / "policy.json"
    policy_path.write_text(json.dumps({
        "version": FEATURE_VERSION,
        "source": "CORPORATION_FAVORITA public demand mirror; no stock, cost, margin, or inventory fields",
        "questions": ["series_decision", "handling_risk", "exception_needed"],
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "thresholds": {"demand_drop_ratio": 0.75, "replenishment_candidate_ratio": 1.10, "candidate_active_day_share": 0.35, "handling_risk_sales_cv": 1.00, "handling_risk_active_day_share": 0.25, "exception_sales_cv": 1.50, "exception_active_day_share": 0.15, "exclude_active_day_share": 0.10},
        "route_precedence": ["error", "block", "review", "accept"],
        "honesty_note": "demand_drop_alert and replenishment_candidate are demand proxies; neither is a stockout or inventory count.",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "retail_rows": len(selected_retail), "retail_sha256": sha256(retail_out),
        "tickets_rows": len(tickets), "tickets_sha256": sha256(tickets_out),
        "retail_raw_sha256": sha256(retail_raw), "tickets_raw_sha256": sha256(tickets_raw),
        "retail_window": [start.isoformat(), end.isoformat()],
    }, ensure_ascii=False))
    if args.delete_raw:
        raw_root = args.raw_dir.resolve()
        for path in (retail_raw, tickets_raw):
            try:
                path.resolve().relative_to(raw_root)
            except ValueError:
                print(f"raw_kept_outside_raw_dir={path}")
                continue
            path.unlink(missing_ok=True)
        print("raw_deleted=true")


if __name__ == "__main__":
    main()
