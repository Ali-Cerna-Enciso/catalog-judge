from __future__ import annotations

from typesafe_sdk import Choice, Noul, Score

from catalog_judge.jev_client import normalize_response
from catalog_judge.prompts import RETAIL_QUESTION_IDS, TICKET_QUESTION_IDS, retail_questions, tickets_questions


def test_retail_contract_has_three_atomic_questions() -> None:
    questions = retail_questions()
    assert tuple(questions) == RETAIL_QUESTION_IDS
    assert len(questions) == 3
    assert isinstance(questions["series_decision"], Choice)
    assert isinstance(questions["handling_risk"], Noul)
    assert isinstance(questions["exception_needed"], Noul)
    assert "family" not in questions


def test_ticket_contract_has_exactly_ten_atomic_questions() -> None:
    questions = tickets_questions()
    assert tuple(questions) == TICKET_QUESTION_IDS
    assert len(questions) == 10
    assert len(set(TICKET_QUESTION_IDS)) == 10
    assert not {"apology_present", "sentiment", "routing_hint", "severity", "criticality", "time_sensitive", "requires_human"} & set(questions)
    assert {"is_ambiguous", "is_contradictory", "needs_specialist"} <= set(questions)
    assert sum(isinstance(value, Choice) for value in questions.values()) == 3
    assert sum(isinstance(value, Noul) for value in questions.values()) == 6
    assert sum(isinstance(value, Score) for value in questions.values()) == 1


def test_contract_normalization_rejects_missing_answer() -> None:
    questions = retail_questions()
    try:
        normalize_response({"answers": {}}, questions, RETAIL_QUESTION_IDS)
    except Exception as exc:
        assert "faltan" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("una respuesta incompleta no debe pasar")
