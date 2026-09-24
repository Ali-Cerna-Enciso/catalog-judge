from __future__ import annotations

from typing import Any

import pandas as pd

from catalog_judge.csv_io import normalize_tickets_dataframe, read_csv
from catalog_judge.jev_client import DeterministicMockJev
from catalog_judge.pipeline import execute_rows
from catalog_judge.prompts import tickets_questions
from catalog_judge.tickets import build_ticket_state


def test_one_call_per_row_tickets_only_jev(retail_sample, tickets_sample) -> None:
    retail_rows = read_csv(retail_sample, "retail", limit=5)
    ticket_rows = read_csv(tickets_sample, "tickets", limit=7)
    retail_backend = DeterministicMockJev()
    ticket_backend = DeterministicMockJev()
    retail = execute_rows("retail", retail_rows, retail_backend, workers=3, mock=True)
    tickets = execute_rows("tickets", ticket_rows, ticket_backend, workers=3, mock=True)
    assert retail_backend.call_count == 0
    assert ticket_backend.call_count == 7
    assert all(item.status == "ok" and len(item.judgments) == 3 for item in retail.results)
    assert all(item.backend == "code" and item.mock is False for item in retail.results)
    assert all(item.status == "ok" and len(item.judgments) == 10 for item in tickets.results)
    assert all(count == 10 for count in ticket_backend.question_counts)
    assert all(item.computed.get("destination") for item in tickets.results)
    assert all(item.computed.get("priority") for item in tickets.results)


def test_area_runner_up_and_margin_land_in_computed(retail_sample, tickets_sample) -> None:
    rows = read_csv(tickets_sample, "tickets", limit=5)
    report = execute_rows("tickets", rows, DeterministicMockJev(), workers=1, mock=True)
    for item in report.results:
        runner = item.computed.get("area_runner_up")
        assert isinstance(runner, dict) and runner["choice"]
        assert 0 <= runner["probability"] <= 1
        margin = item.computed.get("area_margin")
        assert margin is not None and margin >= 0
        assert round(margin, 4) == margin


def test_ticket_state_includes_team_policy_kb(tickets_sample) -> None:
    row = read_csv(tickets_sample, "tickets", limit=1)[0]
    state = build_ticket_state(row)
    policy = state["team_policy"]
    assert set(policy) >= {"standard_action", "clarification", "immediate_action", "no_action"}
    # La KB no filtra gold ni cortes: ni expected_* ni números de umbral.
    assert "expected_" not in str(policy)
    assert "threshold" not in str(policy).lower()
    assert set(state) == {"ticket", "team_policy"}


def test_mock_does_not_consume_gold_hints(tickets_sample) -> None:
    row = read_csv(tickets_sample, "tickets", limit=1)[0]
    state = build_ticket_state(row)
    backend = DeterministicMockJev()
    questions = tickets_questions()
    first = backend.classify(state, questions, {"expected_area": "seguridad", "expected_route": "block"})
    second = backend.classify(state, questions, {"expected_area": "logistica", "expected_route": "accept"})
    assert first.answers == second.answers


def test_expected_columns_are_not_sent_to_backend(retail_sample) -> None:
    rows = read_csv(retail_sample, "retail", limit=1)
    captured: list[dict[str, Any]] = []

    class Recorder:
        def classify(self, state, questions, hints=None):
            captured.append(state)
            return DeterministicMockJev().classify(state, questions, hints)

    report = execute_rows("retail", rows, Recorder(), workers=1, mock=True)
    assert captured == []
    assert report.results[0].backend == "code"
    assert "expected_" not in str(report.results[0].computed)


def test_optional_human_signal_columns_are_read_only_when_present() -> None:
    """v7: `expected_ambiguous`/`expected_contradictory` son opcionales."""
    base = {
        "source_id": "v7-optional-001",
        "source_dataset": "catalog-judge/ticket-rubric-v2",
        "subject_es": "Consulta de estado",
        "body_es": "Quisiera saber en qué estado quedó mi caso.",
        "texto": "Consulta de estado\nQuisiera saber en qué estado quedó mi caso.",
        "expected_area": "atencion_cliente",
        "expected_intent": "consulta",
        "expected_urgency": "low",
        "expected_human": "True",
        "expected_security_legal": "False",
        "expected_refund": "False",
        "expected_actionability": "standard_action",
        "expected_technical_repro": "False",
        "expected_route": "review",
    }
    # Las 2 columnas extra no rompen la validación de esquema y se parsean
    # como booleanos (mismo patrón que `expected_human`: strings "True"/"False").
    with_extra = normalize_tickets_dataframe(pd.DataFrame([dict(base, expected_ambiguous="True", expected_contradictory="False")]))
    assert with_extra[0]["expected_ambiguous"] is True
    assert with_extra[0]["expected_contradictory"] is False
    # Sin esas columnas, la fila no las trae.
    without = normalize_tickets_dataframe(pd.DataFrame([base]))
    assert "expected_ambiguous" not in without[0]
    assert "expected_contradictory" not in without[0]


def test_ticket_pii_is_sanitized_before_backend_call() -> None:
    frame = pd.DataFrame([{
        "source_id": "synthetic-001",
        "source_dataset": "synthetic-test",
        "subject_es": "Consulta de prueba",
        "body_es": "Escriban a prueba@example.invalid o +51 987 654 321; DNI 12345678.",
        "texto": "Consulta de prueba\nEscriban a prueba@example.invalid o +51 987 654 321; DNI 12345678.",
        "expected_area": "seguridad",
    }])
    rows = normalize_tickets_dataframe(frame)
    captured: list[dict[str, Any]] = []

    class Recorder:
        def classify(self, state, questions, hints=None):
            captured.append(state)
            return DeterministicMockJev().classify(state, questions, hints)

    report = execute_rows("tickets", rows, Recorder(), workers=1, mock=True)
    assert report.results[0].status == "ok"
    serialized = str(captured[0])
    assert "prueba@example.invalid" not in serialized
    assert "987 654 321" not in serialized
    assert "12345678" not in serialized
    assert "PLACEHOLDER" in captured[0]["ticket"]["body"]
    assert "texto" not in captured[0]
    assert "local_pii_detected" not in captured[0]
    assert report.results[0].computed["local_pii_detected"] is True
