from __future__ import annotations

from catalog_judge.aggregation import summarize_results
from catalog_judge.csv_io import read_csv
from catalog_judge.evaluation import build_evidence, evaluate_results
from catalog_judge.jev_client import DeterministicMockJev
from catalog_judge.pipeline import execute_rows


def test_contract_coverage_is_separate_from_quality(tickets_sample) -> None:
    rows = read_csv(tickets_sample, "tickets", limit=20)
    report = execute_rows("tickets", rows, DeterministicMockJev(), workers=2, mock=True)
    summary = summarize_results(report.results)
    assert summary["requests_completed"] == 20
    assert summary["valid_responses"] == 20
    assert summary["contract_coverage"] == 1.0
    assert "coverage" not in summary
    metrics = evaluate_results(report.results, "tickets")
    assert metrics["n"] == 20
    assert "area_accuracy" in metrics
    assert "route_macro_f1" in metrics
    assert "actionability_adjacent_accuracy" in metrics
    assert "gold_accept_recall" in metrics
    assert "MOCK_EVALUATION_ONLY" in " ".join(metrics["warnings"])


def test_export_omits_input_text_by_default(tmp_path, tickets_sample) -> None:
    from catalog_judge.csv_io import read_results, write_results

    rows = read_csv(tickets_sample, "tickets", limit=3)
    report = execute_rows("tickets", rows, DeterministicMockJev(), workers=1, mock=True)
    path = write_results(report.results, tmp_path / "result.json")
    payload = path.read_text(encoding="utf-8")
    assert "redacted_text" not in payload
    assert len(read_results(path)) == 3


def test_technical_repro_gold_reaches_the_evaluator(tickets_sample) -> None:
    from catalog_judge.tickets import expected_fields

    rows = read_csv(tickets_sample, "tickets", limit=5)
    assert rows, "el fixture debe tener filas de tickets"
    for row in rows:
        assert "expected_technical_repro" in row, "el CSV debe traer el gold de technical_repro"
        assert "expected_technical_repro" in expected_fields(row), "expected_fields no debe soltar el gold de technical_repro"
    report = execute_rows("tickets", rows, DeterministicMockJev(), workers=1, mock=True)
    metrics = evaluate_results(report.results, "tickets")
    assert metrics["technical_repro"]["n"] == len(rows)
    assert metrics["technical_repro"]["missing_predictions"] == 0


def test_evidence_contains_hashes_but_no_input_text(tmp_path, tickets_sample) -> None:
    rows = read_csv(tickets_sample, "tickets", limit=1)
    report = execute_rows("tickets", rows, DeterministicMockJev(), workers=1, mock=True)
    payload = build_evidence(
        report.results,
        domain="tickets",
        input_path=tickets_sample,
        model="jev-1.13.0",
        split="holdout",
    )
    text = str(payload)
    assert "redacted_text" not in text
    assert "subject_es" not in text
    assert "body_es" not in text
    assert payload["metadata"]["prompt_sha256"]
    assert payload["metadata"]["threshold_sha256"]
    assert payload["metadata"]["dataset_sha256"]
    assert payload["metadata"]["state_schema_sha256"]
    assert payload["metadata"]["state_schema_sha256"] != payload["metadata"]["prompt_sha256"]
    assert payload["requests"][0]["expected"]


def test_human_metric_composes_the_three_signals(tickets_sample) -> None:
    rows = read_csv(tickets_sample, "tickets", limit=10)
    report = execute_rows("tickets", rows, DeterministicMockJev(), workers=1, mock=True)
    metrics = evaluate_results(report.results, "tickets")
    # Las filas traen las tres señales: la métrica no cae al fallback legacy.
    assert metrics["requires_human"]["n"] == len(rows)
    assert metrics["requires_human"]["missing_predictions"] == 0
    assert "requires_human_accuracy" in metrics


def test_legacy_requires_human_evidence_still_scores() -> None:
    from catalog_judge.contracts import Judgment, RowResult
    from catalog_judge.evaluation import _human_signal_composition

    legacy_yes = RowResult(
        domain="tickets",
        row_id="legacy-1",
        route="review",
        status="ok",
        judgments=[Judgment("requires_human", "noul", 0.9, noul=0.9)],
    )
    legacy_no = RowResult(
        domain="tickets",
        row_id="legacy-2",
        route="accept",
        status="ok",
        judgments=[Judgment("requires_human", "noul", 0.1, noul=0.1)],
    )
    assert _human_signal_composition(legacy_yes) is True
    assert _human_signal_composition(legacy_no) is False

    # Con las tres señales presentes mandan ellas (OR), no el legacy.
    v6_signals = RowResult(
        domain="tickets",
        row_id="v6-1",
        route="accept",
        status="ok",
        judgments=[
            Judgment("is_ambiguous", "noul", 0.1, noul=0.1),
            Judgment("is_contradictory", "noul", 0.1, noul=0.1),
            Judgment("needs_specialist", "noul", 0.9, noul=0.9),
        ],
    )
    assert _human_signal_composition(v6_signals) is True

    mixed = RowResult(
        domain="tickets",
        row_id="v6-2",
        route="accept",
        status="ok",
        judgments=[
            Judgment("requires_human", "noul", 0.9, noul=0.9),
            Judgment("is_ambiguous", "noul", 0.1, noul=0.1),
            Judgment("is_contradictory", "noul", 0.1, noul=0.1),
            Judgment("needs_specialist", "noul", 0.1, noul=0.1),
        ],
    )
    assert _human_signal_composition(mixed) is False
