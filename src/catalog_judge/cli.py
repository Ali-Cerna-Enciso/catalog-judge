"""CLI de ``catalog-judge`` para CI, demos y evaluaciones."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from .aggregation import summarize_results
from .config import DEFAULT_MODEL, Settings
from .csv_io import write_results
from .evaluation import evaluate_file
from .pipeline import run_retail, run_tickets
from .routing import RoutingThresholds


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _add_threshold_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workers", type=int, default=4, help="filas concurrentes (default: 4)")
    parser.add_argument("--limit", type=int, default=None, help="procesa como máximo N filas")
    parser.add_argument("--retail-choice-review", type=float, default=0.50)
    parser.add_argument("--retail-choice-accept", type=float, default=0.75)
    parser.add_argument("--retail-handling-noul", type=float, default=0.65)
    parser.add_argument("--retail-exception-noul", type=float, default=0.70)
    parser.add_argument("--ticket-choice-review", type=float, default=0.60)
    parser.add_argument("--ticket-choice-accept", type=float, default=0.75)
    parser.add_argument("--ticket-choice-sensitive-accept", type=float, default=0.85)
    parser.add_argument("--ticket-specialist-noul", type=float, default=0.50)
    parser.add_argument("--ticket-contradictory-noul", type=float, default=0.50)
    parser.add_argument("--ticket-ambiguous-noul", type=float, default=0.85)
    parser.add_argument("--ticket-security-noul", type=float, default=0.65)
    parser.add_argument("--ticket-refund-noul", type=float, default=0.50)
    parser.add_argument("--ticket-urgency-high", type=float, default=2.00)
    parser.add_argument("--ticket-actionability-review", type=float, default=1.00)
    parser.add_argument("--ticket-technical-repro-review", type=float, default=0.35)


def _thresholds(args: argparse.Namespace) -> RoutingThresholds:
    if not 0 <= args.retail_choice_review <= args.retail_choice_accept <= 1:
        raise ValueError("los cortes retail choice deben ser review <= accept y estar entre 0 y 1")
    if not 0 <= args.ticket_choice_review <= args.ticket_choice_accept <= 1:
        raise ValueError("los cortes tickets choice deben ser review <= accept y estar entre 0 y 1")
    if not 0 <= args.ticket_choice_sensitive_accept <= 1:
        raise ValueError("el corte de confidence para destino sensible debe estar entre 0 y 1")
    for value in (
        args.retail_handling_noul,
        args.retail_exception_noul,
        args.ticket_specialist_noul,
        args.ticket_contradictory_noul,
        args.ticket_ambiguous_noul,
        args.ticket_security_noul,
        args.ticket_refund_noul,
        args.ticket_technical_repro_review,
    ):
        if not 0 <= value <= 1:
            raise ValueError("los cortes Noul deben estar entre 0 y 1")
    return RoutingThresholds(
        retail_choice_review=args.retail_choice_review,
        retail_choice_accept=args.retail_choice_accept,
        retail_handling_noul=args.retail_handling_noul,
        retail_exception_noul=args.retail_exception_noul,
        ticket_choice_review=args.ticket_choice_review,
        ticket_choice_accept=args.ticket_choice_accept,
        ticket_choice_sensitive_accept=args.ticket_choice_sensitive_accept,
        ticket_specialist_noul=args.ticket_specialist_noul,
        ticket_contradictory_noul=args.ticket_contradictory_noul,
        ticket_ambiguous_noul=args.ticket_ambiguous_noul,
        ticket_security_noul=args.ticket_security_noul,
        ticket_refund_noul=args.ticket_refund_noul,
        ticket_urgency_high=args.ticket_urgency_high,
        ticket_actionability_review=args.ticket_actionability_review,
        ticket_technical_repro_review=args.ticket_technical_repro_review,
    )


def _mode_warning(mode: str, domain: str) -> None:
    if domain == "retail":
        print("RETAIL: política de código sobre features de demanda; no envía filas a Jev.", file=sys.stderr)
        return
    if mode == "live":
        print("AVISO: live enviará state público a TypeSafe; sólo usa datos autorizados.", file=sys.stderr)
    else:
        print("MOCK: heurística local; no realiza red y no mide Jev real.", file=sys.stderr)


def _emit_report(report: Any, output: str | None) -> None:
    summary = summarize_results(report.results)
    if output:
        path = write_results(report.results, output, include_text=False)
        print(json.dumps({"summary": summary, "output": str(path)}, ensure_ascii=False))
    else:
        print(json.dumps(summary, ensure_ascii=False))


def _run_domain(args: argparse.Namespace, domain: str) -> int:
    settings = Settings.from_env()
    if domain == "tickets" and args.mode == "live" and not (args.allow_remote or settings.allow_remote):
        print("ERROR: live requiere --allow-remote o CATALOG_JUDGE_ALLOW_REMOTE=1.", file=sys.stderr)
        return 2
    _mode_warning(args.mode, domain)
    runner = run_retail if domain == "retail" else run_tickets
    report = runner(
        args.input,
        mode=args.mode,
        settings=settings,
        allow_remote=args.allow_remote,
        limit=args.limit,
        workers=args.workers,
        thresholds=_thresholds(args),
    )
    _emit_report(report, args.output)
    return 0 if all(result.status != "error" for result in report.results) else 1


def _doctor() -> int:
    settings = Settings.from_env()
    try:
        sdk_version = version("typesafe-sdk")
    except PackageNotFoundError:
        sdk_version = "not-installed"
    payload = settings.public_summary()
    payload["typesafe_sdk"] = sdk_version
    payload["default_model"] = DEFAULT_MODEL
    payload["note"] = "No se hace red ni se imprime la API key en este comando."
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _sample_path(relative: str) -> Path:
    for root in (_repo_root(), Path.cwd()):
        candidate = root / relative
        if candidate.exists():
            return candidate
    return _repo_root() / relative


def _demo(args: argparse.Namespace) -> int:
    retail_input = _sample_path("retail/data/favorita_demand_96.csv")
    tickets_input = _sample_path("tickets/data/tickets_100.csv")
    if not retail_input.exists() or not tickets_input.exists():
        print("ERROR: faltan los fixtures públicos; ejecuta scripts/prepare_public_fixtures.py.", file=sys.stderr)
        return 2
    print("DEMO: retail = política de código; tickets = mock Jev. El mock no es evidencia de Jev.", file=sys.stderr)
    for domain, source in (("retail", retail_input), ("tickets", tickets_input)):
        runner = run_retail if domain == "retail" else run_tickets
        report = runner(source, mode="mock", limit=args.limit, workers=args.workers)
        out = None
        if args.output:
            base = Path(args.output)
            out = base / f"{domain}{base.suffix or '.csv'}"
        _emit_report(report, str(out) if out else None)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="catalog-judge",
        description="Clasificación por fila: retail en código, tickets con Jev y ruteo determinista.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="demo offline de retail y tickets")
    demo.add_argument("--limit", type=int, default=12)
    demo.add_argument("--workers", type=int, default=4)
    demo.add_argument("--output", type=Path, default=None)

    for domain, help_text in (("retail", "procesa fixture de demanda Favorita"), ("tickets", "procesa tickets públicos curados")):
        command = sub.add_parser(domain, help=help_text)
        command.add_argument("--input", required=True, type=Path)
        command.add_argument("--mode", choices=("mock", "live"), default="mock")
        command.add_argument("--allow-remote", action="store_true", help="autoriza envío a TypeSafe")
        command.add_argument("--output", type=Path, default=None)
        _add_threshold_args(command)

    evaluate = sub.add_parser("evaluate", help="calcula métricas sobre un export propio")
    evaluate.add_argument("--input", required=True, type=Path)
    evaluate.add_argument("--domain", choices=("retail", "tickets"), default=None)
    evaluate.add_argument("--json", action="store_true")

    sub.add_parser("doctor", help="comprueba configuración local sin red")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            return _demo(args)
        if args.command == "doctor":
            return _doctor()
        if args.command == "evaluate":
            print(json.dumps(evaluate_file(args.input, domain=args.domain), ensure_ascii=False, indent=2 if args.json else None))
            return 0
        if args.command in {"retail", "tickets"}:
            return _run_domain(args, args.command)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    parser.error("comando desconocido")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
