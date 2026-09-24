from __future__ import annotations

from catalog_judge.contracts import Judgment
from catalog_judge.prompts import tickets_questions
from catalog_judge.retail import build_retail_state, calculate_retail_metrics, classify_retail_policy, demand_bands
from catalog_judge.routing import normalized_score, noul_band, route_tickets


def test_demand_bands_align_with_policy_edges() -> None:
    row = {
        "series_id": "s1",
        "store_nbr": 1,
        "family": "DELI",
        "avg_sales": 10.0,
        "sales_cv": 1.0,
        "active_day_share": 0.24,
        "promo_share": 0.50,
        "recent_vs_previous_ratio": 0.74,
    }
    metrics = calculate_retail_metrics(row)
    assert metrics["demand_bands"] == {
        "volume": "baja",
        "trend": "caida",
        "presence": "muy_baja",
        "volatility": "extrema",
        "promo": "alta",
    }
    state = build_retail_state(row)
    assert state["demand_bands"] == metrics["demand_bands"]
    assert "expected_series_decision" not in str(state)
    policy = classify_retail_policy(row)
    assert policy["judge"] == "code"
    assert policy["series_decision"] == "review"
    assert policy["handling_risk"] is True
    assert policy["exception_needed"] is True


def test_demand_band_boundaries() -> None:
    assert demand_bands(4.9, 0.44, 0.24, 0.05, 1.0)["volume"] == "muy_baja"
    assert demand_bands(5.0, 0.45, 0.25, 0.06, 1.0)["volume"] == "baja"
    assert demand_bands(10.0, 0.75, 0.60, 0.39, 1.10)["trend"] == "creciente"
    assert demand_bands(10.0, 0.75, 0.60, 0.39, 0.75)["trend"] == "estable"
    assert demand_bands(10.0, 1.0, 0.60, 0.39, 1.0)["volatility"] == "extrema"


def test_ticket_prompts_keep_structured_criteria() -> None:
    tickets = tickets_questions()
    assert set(tickets["urgency"].criteria[0]) >= {"what", "examples"}
    assert set(tickets["actionability"].criteria["standard_action"]) >= {"what", "examples", "not_for"}
    assert "not_for" in tickets["area"].criteria["pagos"]
    assert "never as a low-confidence fallback" not in str(tickets["area"].criteria["otro"])
    # Las tres señales humanas (v6) reemplazan a requires_human con rúbrica propia.
    assert "requires_human" not in tickets
    for question_id in ("is_ambiguous", "is_contradictory", "needs_specialist"):
        assert set(tickets[question_id].criteria) >= {"true", "false"}
        assert tickets[question_id].instructions["question"]


def test_ticket_medium_confidence_marks_without_veto() -> None:
    from tests.test_routing import ticket_judgments

    judgments = ticket_judgments()
    judgments[0] = Judgment("area", "choice", "tecnologia", confidence=0.64, choice="tecnologia")
    route, reasons = route_tickets(judgments, {})
    assert route == "accept"
    assert any("confidence_media" in reason for reason in reasons)


def test_ticket_low_confidence_still_forces_review() -> None:
    from tests.test_routing import ticket_judgments

    judgments = ticket_judgments()
    judgments[0] = Judgment("area", "choice", "tecnologia", confidence=0.40, choice="tecnologia")
    route, reasons = route_tickets(judgments, {})
    assert route == "review"
    assert any("confidence_bajo" in reason for reason in reasons)


def test_ticket_human_uncertain_band_marks_without_veto() -> None:
    from tests.test_routing import ticket_judgments

    # 0.40 cae en la banda de incertidumbre de needs_specialist (0.30–0.50).
    judgments = ticket_judgments(specialist=0.40, actionability="standard_action", urgency=1.0)
    route, reasons = route_tickets(judgments, {})
    assert route == "accept"
    assert any("needs_specialist.incertidumbre=" in reason for reason in reasons)


def test_score_normalization_and_noul_bands() -> None:
    answer = Judgment("urgency", "score", 1.5, confidence=0.6, score=1.5)
    assert normalized_score(answer, 4) == 0.5
    assert noul_band(0.2, 0.45, 0.65) == "no"
    assert noul_band(0.5, 0.45, 0.65) == "incierto"
    assert noul_band(0.8, 0.45, 0.65) == "si"
