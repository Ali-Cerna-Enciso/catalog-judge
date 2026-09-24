"""Congela el protocolo v7 antes de cualquier llamada live de tickets.

Tickets confirmation = 50 textos nuevos (`tickets_v7_50.csv`), contrato de
10 preguntas, corte `is_ambiguous` 0.85. Cada manifest se congela una sola
vez: si ya hay uno en disco, el script exige archivarlo junto a su evidence
en evaluations/archive/ y actualizar el test de manifest.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from catalog_judge.config import DEFAULT_MODEL
from catalog_judge.evaluation import dataset_hash, prompt_hash, threshold_hash
from catalog_judge.routing import DEFAULT_THRESHOLDS

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evaluations" / "holdout_manifest.json"
SOURCES = {
    "tickets": ROOT / "tickets" / "data" / "tickets_v7_50.csv",
    "retail": ROOT / "retail" / "data" / "favorita_demand_96.csv",
}
LIMITS = {"tickets": 50, "retail": 20}
CONFIRMATION_SPLIT = {"tickets": "confirmation", "retail": "holdout"}


def main() -> None:
    if OUT.exists():
        try:
            previous = json.loads(OUT.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = {}
        raise SystemExit(
            f"ERROR: ya existe un manifest congelado (protocolo {previous.get('protocol', '?')}) en {OUT}. "
            "Archívalo junto a su evidence en evaluations/archive/ y actualiza tests/test_manifest.py "
            "antes de congelar de nuevo: un lote ya medido no se re-mide."
        )
    missing = [str(path) for path in SOURCES.values() if not path.exists()]
    if missing:
        raise SystemExit(
            "ERROR: falta el lote del protocolo v7: "
            + ", ".join(missing)
            + ". Cura primero el lote nuevo (no se congela sobre un lote ya medido)."
        )
    datasets: dict[str, dict[str, object]] = {}
    for domain, path in SOURCES.items():
        frame = pd.read_csv(path, usecols=["evaluation_split"])
        counts = frame["evaluation_split"].value_counts().to_dict()
        datasets[domain] = {
            "path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "sha256": dataset_hash(path),
            "dev": int(counts.get("dev", 0)),
            "holdout": int(counts.get("holdout", 0)),
            "confirmation": int(counts.get("confirmation", 0)),
            "confirmation_split": CONFIRMATION_SPLIT[domain],
            "limit": LIMITS[domain],
        }
    payload = {
        "version": "confirmation-manifest-v7",
        "protocol": "v7",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "model": DEFAULT_MODEL,
        "jev_domains": ["tickets"],
        "code_domains": ["retail"],
        "prompt_sha256": {domain: prompt_hash(domain) for domain in SOURCES},
        "threshold_sha256": threshold_hash(DEFAULT_THRESHOLDS),
        "datasets": datasets,
        "confirmation_split": CONFIRMATION_SPLIT,
        "no_tuning_on_confirmation": True,
        "no_tuning_on_holdout": True,
        "note": (
            "Tickets confirmation = lote nuevo rubricado v2 con columnas "
            "expected_ambiguous/expected_contradictory. Corte is_ambiguous 0.85 "
            "(candidato post-hoc de v6, una sola medición). No se re-miden v4/v5/v6. "
            "Retail es política de código."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"manifest": str(OUT), "model": DEFAULT_MODEL, "protocol": "v7"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
