"""Ejecuta una evaluación congelada: tickets live (Jev) o retail (código).

Tickets: confirmation split `confirmation` (lote v7), key vía ``dotenv_values``.
Retail: no llama a TypeSafe; no necesita key.

Guard: exige un manifest `protocol == "v7"` encadenado con el código vivo
(prompts + KB del state + thresholds). Un manifest de otro protocolo en
disco bloquea el live hasta re-congelar con el lote nuevo.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import replace
from pathlib import Path

from dotenv import dotenv_values

from catalog_judge.config import DEFAULT_MODEL, Settings
from catalog_judge.csv_io import read_csv
from catalog_judge.evaluation import (
    build_evidence,
    dataset_hash,
    file_sha256,
    prompt_hash,
    threshold_hash,
    write_evidence,
)
from catalog_judge.jev_client import JevBackend
from catalog_judge.pipeline import execute_rows
from catalog_judge.routing import DEFAULT_THRESHOLDS

ROOT = Path(__file__).resolve().parents[1]
LIMITS = {"retail": 20, "tickets": 50}
DEFAULTS = {
    "retail": ROOT / "retail" / "data" / "favorita_demand_96.csv",
    "tickets": ROOT / "tickets" / "data" / "tickets_v7_50.csv",
}
CONFIRMATION_SPLIT = {"tickets": "confirmation", "retail": "holdout"}


def update_summary(evidence_dir: Path) -> None:
    runs = []
    payload: dict = {}
    for path in sorted(evidence_dir.glob("*_live_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        runs.append({
            "file": path.name,
            "metadata": payload.get("metadata", {}),
            "summary": payload.get("summary", {}),
        })
    (evidence_dir / "summary.json").write_text(
        json.dumps({"updated_at": payload.get("metadata", {}).get("evaluated_at"), "runs": runs}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def verify_manifest(manifest_path: Path, domain: str, input_path: Path, split_count: int) -> dict:
    if not manifest_path.exists():
        raise ValueError("falta el manifiesto congelado; ejecuta scripts/freeze_evaluation.py")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("protocol") != "v7":
        raise ValueError("el manifiesto no es protocolo v7")
    if manifest.get("no_tuning_on_confirmation") is not True:
        raise ValueError("el manifiesto no declara confirmation sin tuning")
    if domain == "tickets" and manifest.get("model") != DEFAULT_MODEL:
        raise ValueError("el modelo del manifiesto no coincide")
    datasets = manifest.get("datasets", {})
    expected = datasets.get(domain)
    if not isinstance(expected, dict):
        raise ValueError("el manifiesto no contiene este dominio")
    expected_path = (ROOT / str(expected.get("path", ""))).resolve()
    if input_path.resolve() != expected_path:
        raise ValueError("el input no coincide con el dataset congelado")
    if expected.get("sha256") != dataset_hash(input_path):
        raise ValueError("el hash del dataset cambió después del freeze")
    expected_split = str(expected.get("confirmation_split") or CONFIRMATION_SPLIT[domain])
    if expected_split != CONFIRMATION_SPLIT[domain]:
        raise ValueError("el split de confirmation cambió después del freeze")
    if split_count < int(expected.get("limit", LIMITS[domain])):
        raise ValueError("el tamaño del split de confirmation es insuficiente")
    if manifest.get("prompt_sha256", {}).get(domain) != prompt_hash(domain):
        raise ValueError("el contrato/prompt cambió después del freeze")
    if manifest.get("threshold_sha256") != threshold_hash(DEFAULT_THRESHOLDS):
        raise ValueError("los thresholds cambiaron después del freeze")
    return manifest


def _clear_proxy() -> None:
    for proxy_name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        os.environ.pop(proxy_name, None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("domain", choices=sorted(LIMITS))
    parser.add_argument("--env-file", type=Path, default=None)
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--allow-remote", action="store_true")
    parser.add_argument("--manifest", type=Path, default=ROOT / "evaluations" / "holdout_manifest.json")
    args = parser.parse_args(argv)
    max_rows = LIMITS[args.domain]
    requested = args.limit if args.limit is not None else max_rows
    if requested < 1 or requested > max_rows:
        print(f"ERROR: limit debe estar entre 1 y {max_rows}", file=sys.stderr)
        return 2
    input_path = args.input or DEFAULTS[args.domain]
    if not input_path.exists():
        print(
            f"ERROR: falta el dataset {input_path}; el lote v7 aún no existe. "
            "Cura el lote nuevo y congela el protocolo con scripts/freeze_evaluation.py",
            file=sys.stderr,
        )
        return 2
    split_name = CONFIRMATION_SPLIT[args.domain]
    split_rows = [row for row in read_csv(input_path, args.domain) if row.get("evaluation_split") == split_name]
    if len(split_rows) < requested:
        print(f"ERROR: split {split_name} insuficiente: {len(split_rows)} < {requested}", file=sys.stderr)
        return 2
    try:
        verify_manifest(args.manifest, args.domain, input_path, len(split_rows))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: protocolo congelado no válido ({exc})", file=sys.stderr)
        return 2
    rows = split_rows[:requested]
    _clear_proxy()
    if args.domain == "retail":
        report = execute_rows("retail", rows, None, workers=max(1, min(args.workers, 8)), limit=None, mock=False)
        model = "code-policy"
        split_label = "confirmation"
    else:
        if not args.allow_remote:
            print("ERROR: live de tickets requiere --allow-remote", file=sys.stderr)
            return 2
        if args.env_file is None:
            print("ERROR: tickets live requiere --env-file", file=sys.stderr)
            return 2
        values = dotenv_values(args.env_file)
        key = values.get("TYPESAFE_API_KEY")
        if not key or not str(key).strip():
            print("ERROR: no se encontró TYPESAFE_API_KEY en el archivo indicado", file=sys.stderr)
            return 2
        os.environ["TYPESAFE_API_KEY"] = str(key).strip()
        os.environ["CATALOG_JUDGE_ALLOW_REMOTE"] = "1"
        os.environ["TYPESAFE_LOG_LEVEL"] = "off"
        settings = replace(
            Settings.from_env(args.env_file),
            model=DEFAULT_MODEL,
            allow_remote=True,
            log_level="off",
        )
        try:
            backend = JevBackend(settings, allow_remote=True)
            report = execute_rows("tickets", rows, backend, workers=max(1, min(args.workers, 8)), limit=None, mock=False)
        except Exception as exc:
            print(f"ERROR: no se pudo inicializar live ({type(exc).__name__})", file=sys.stderr)
            return 1
        model = settings.model
        split_label = "confirmation"
    output = args.output or ROOT / "evaluations" / f"{args.domain}_live_{requested}.json"
    payload = build_evidence(
        report.results,
        domain=args.domain,
        input_path=input_path,
        model=model,
        split=split_label,
        thresholds=DEFAULT_THRESHOLDS,
    )
    manifest_hash = file_sha256(args.manifest)
    payload["metadata"]["holdout_manifest_sha256"] = manifest_hash
    payload["metadata"]["confirmation_split"] = split_name
    if isinstance(payload.get("summary", {}).get("metadata"), dict):
        payload["summary"]["metadata"]["holdout_manifest_sha256"] = manifest_hash
        payload["summary"]["metadata"]["confirmation_split"] = split_name
    write_evidence(payload, output)
    update_summary(output.parent)
    print(json.dumps({
        "domain": args.domain,
        "n": payload["summary"].get("n"),
        "valid_responses": payload["summary"].get("valid_responses"),
        "contract_coverage": payload["summary"].get("contract_coverage"),
        "error_count": payload["summary"].get("error_count"),
        "output": str(output),
    }, ensure_ascii=False))
    return 0 if payload["summary"].get("error_count", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
