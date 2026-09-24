"""Orquestación común: una fila -> un request -> contrato -> ruta."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import Settings
from .contracts import RowResult
from .csv_io import read_csv
from .jev_client import (
    BackendError,
    ContractError,
    DeterministicMockJev,
    JevBackend,
    JudgmentBackend,
    backend_request_id,
    call_backend,
    normalize_response,
)
from .privacy import contains_pii
from .prompts import TICKET_QUESTION_IDS, tickets_questions
from .retail import classify_retail_policy, retail_policy_judgments, retail_preview, retail_row_id
from .retail import expected_fields as retail_expected
from .routing import (
    DEFAULT_THRESHOLDS,
    RoutingThresholds,
    route_tickets,
    ticket_destination,
    ticket_priority,
)
from .tickets import build_ticket_state, ticket_preview, ticket_row_id, ticket_text
from .tickets import expected_fields as ticket_expected


@dataclass
class ExecutionReport:
    domain: str
    mode: str
    workers: int
    results: list[RowResult]

    def __len__(self) -> int:
        return len(self.results)


def _check_workers(workers: int) -> int:
    if workers < 1:
        raise ValueError("workers debe ser >= 1")
    return workers


def _error_result(
    domain: str,
    row_id: str,
    expected: dict[str, Any],
    computed: dict[str, Any] | None,
    mock: bool,
    started: float,
    error: Exception,
) -> RowResult:
    code = error.code if isinstance(error, BackendError) else "contract_error" if isinstance(error, ContractError) else "row_error"
    request_id = error.request_id if isinstance(error, BackendError) else None
    return RowResult(
        domain=domain,  # type: ignore[arg-type]
        row_id=row_id,
        route="error",
        status="error",
        reasons=[code],
        judgments=[],
        computed=computed or {},
        expected=expected,
        latency_ms=round((time.perf_counter() - started) * 1000, 3),
        request_id=request_id,
        error_code=code,
        mock=mock,
        backend="mock" if mock else ("code" if domain == "retail" else "jev"),
    )


def _run_retail_row(row: dict[str, Any], started: float) -> RowResult:
    """Retail es política de código: Favorita no trae texto de SKU para Jev."""
    row_id = retail_row_id(row)
    expected = retail_expected(row)
    policy = classify_retail_policy(row)
    judgments = retail_policy_judgments(policy)
    computed = {key: value for key, value in policy.items() if key != "reasons"}
    return RowResult(
        domain="retail",
        row_id=row_id,
        route=policy["route"],
        status="ok",
        reasons=list(policy["reasons"]),
        judgments=judgments,
        computed=computed,
        expected=expected,
        redacted_text=retail_preview(row),
        latency_ms=round((time.perf_counter() - started) * 1000, 3),
        request_id="code-policy",
        mock=False,
        backend="code",
    )


def _run_one(
    domain: str,
    row: dict[str, Any],
    backend: JudgmentBackend | None,
    questions: dict[str, Any],
    ids: tuple[str, ...],
    thresholds: RoutingThresholds,
    mock: bool,
) -> RowResult:
    started = time.perf_counter()
    row_id = "unknown"
    expected: dict[str, Any] = {}
    computed: dict[str, Any] = {}
    try:
        if domain == "retail":
            return _run_retail_row(row, started)
        if backend is None:
            raise ValueError("tickets requiere un backend de juicio")
        row_id = ticket_row_id(row)
        expected = ticket_expected(row)
        state = build_ticket_state(row)
        computed = {"local_pii_detected": contains_pii(ticket_text(row))}
        # No se pasa gold/hints al backend, ni mock ni live.
        response = call_backend(backend, state, questions, None)
        judgments = normalize_response(response, questions, ids)
        route, reasons = route_tickets(judgments, computed, thresholds)
        answers = {judgment.question_id: judgment for judgment in judgments}
        computed["destination"] = ticket_destination(judgments, thresholds)
        computed["priority"] = ticket_priority(answers["urgency"])
        # Runner-up de `area`: informativo (auditoría de margen), sin veto.
        area_probabilities = answers["area"].probabilities or {}
        if len(area_probabilities) >= 2:
            ranked = sorted(area_probabilities.items(), key=lambda pair: pair[1], reverse=True)
            computed["area_runner_up"] = {"choice": ranked[1][0], "probability": round(ranked[1][1], 4)}
            computed["area_margin"] = round(ranked[0][1] - ranked[1][1], 4)
        action_choice = answers["actionability"].choice
        repro = answers["technical_repro"].noul or 0.0
        computed["needs_clarification"] = action_choice == "clarification"
        computed["technical_repro_low"] = bool(
            answers["area"].choice == "tecnologia" and repro < thresholds.ticket_technical_repro_review
        )
        return RowResult(
            domain="tickets",
            row_id=row_id,
            route=route,
            status="ok",
            reasons=reasons,
            judgments=judgments,
            computed=computed,
            expected=expected,
            redacted_text=ticket_preview(row),
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
            request_id=backend_request_id(response),
            mock=mock,
            backend="mock" if mock else "jev",
        )
    except Exception as exc:
        return _error_result(domain, row_id, expected, computed, mock, started, exc)


def execute_rows(
    domain: str,
    rows: list[dict[str, Any]],
    backend: JudgmentBackend | None,
    *,
    workers: int = 4,
    limit: int | None = None,
    thresholds: RoutingThresholds = DEFAULT_THRESHOLDS,
    mock: bool = False,
) -> ExecutionReport:
    """Ejecuta filas en paralelo. Retail no llama a Jev; tickets sí (1 request / fila)."""
    if domain not in {"retail", "tickets"}:
        raise ValueError("domain debe ser retail o tickets")
    workers = _check_workers(workers)
    if limit is not None and limit < 0:
        raise ValueError("limit debe ser >= 0")
    rows = rows[:limit] if limit is not None else rows
    if domain == "retail":
        questions: dict[str, Any] = {}
        ids: tuple[str, ...] = ()
        mode = "code"
        mock = False
    else:
        if backend is None:
            raise ValueError("tickets requiere un backend de juicio")
        if isinstance(backend, JevBackend):
            with backend.sdk_log_context():
                questions = tickets_questions()
        else:
            questions = tickets_questions()
        ids = TICKET_QUESTION_IDS
        mode = "mock" if mock else "live"
    if workers == 1 or len(rows) <= 1:
        results = [_run_one(domain, row, backend, questions, ids, thresholds, mock) for row in rows]
    else:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="catalog-judge") as executor:
            results = list(executor.map(lambda row: _run_one(domain, row, backend, questions, ids, thresholds, mock), rows))
    return ExecutionReport(domain=domain, mode=mode, workers=workers, results=results)


def make_backend(mode: str, settings: Settings, allow_remote: bool = False) -> JudgmentBackend:
    if mode == "mock":
        return DeterministicMockJev()
    if mode == "live":
        return JevBackend(settings, allow_remote=allow_remote or settings.allow_remote)
    raise ValueError("mode debe ser mock o live")


def run_retail(
    input_path: str | Path,
    *,
    mode: str = "mock",
    settings: Settings | None = None,
    allow_remote: bool = False,
    limit: int | None = None,
    workers: int = 4,
    thresholds: RoutingThresholds = DEFAULT_THRESHOLDS,
) -> ExecutionReport:
    del mode, settings, allow_remote
    rows = read_csv(input_path, "retail", limit=None)
    return execute_rows("retail", rows, None, workers=workers, limit=limit, thresholds=thresholds, mock=False)


def run_tickets(
    input_path: str | Path,
    *,
    mode: str = "mock",
    settings: Settings | None = None,
    allow_remote: bool = False,
    limit: int | None = None,
    workers: int = 4,
    thresholds: RoutingThresholds = DEFAULT_THRESHOLDS,
) -> ExecutionReport:
    settings = settings or Settings.from_env()
    rows = read_csv(input_path, "tickets", limit=None)
    return execute_rows("tickets", rows, make_backend(mode, settings, allow_remote), workers=workers, limit=limit, thresholds=thresholds, mock=mode == "mock")
