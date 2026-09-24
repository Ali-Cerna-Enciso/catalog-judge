from __future__ import annotations

from catalog_judge.contracts import Judgment
from catalog_judge.prompts import TICKET_QUESTION_IDS
from catalog_judge.retail import classify_retail_policy
from catalog_judge.routing import modal_level, route_tickets, ticket_destination, ticket_priority


def ticket_judgments(
    *,
    specialist=0.1,
    ambiguous=0.1,
    contradictory=0.1,
    security=0.1,
    refund=0.1,
    actionability="standard_action",
    urgency=1.0,
    area="tecnologia",
    intent="incidencia",
    technical_repro=0.8,
    area_confidence=0.9,
    intent_confidence=0.9,
    urgency_probabilities=None,
):
    values = {
        "area": Judgment("area", "choice", area, confidence=area_confidence, choice=area),
        "intent": Judgment("intent", "choice", intent, confidence=intent_confidence, choice=intent),
        "urgency": Judgment(
            "urgency",
            "score",
            urgency,
            confidence=0.9,
            score=urgency,
            probabilities=dict(urgency_probabilities) if urgency_probabilities else {},
        ),
        "is_ambiguous": Judgment("is_ambiguous", "noul", ambiguous, noul=ambiguous),
        "is_contradictory": Judgment("is_contradictory", "noul", contradictory, noul=contradictory),
        "needs_specialist": Judgment("needs_specialist", "noul", specialist, noul=specialist),
        "security_legal_risk": Judgment("security_legal_risk", "noul", security, noul=security),
        "refund_or_replacement": Judgment("refund_or_replacement", "noul", refund, noul=refund),
        "actionability": Judgment("actionability", "choice", actionability, confidence=0.9, choice=actionability),
        "technical_repro": Judgment("technical_repro", "noul", technical_repro, noul=technical_repro),
    }
    return [values[qid] for qid in TICKET_QUESTION_IDS]


def test_ticket_standard_route_and_destination() -> None:
    judgments = ticket_judgments()
    route, reasons = route_tickets(judgments, {})
    assert route == "accept"
    assert reasons == ["ruteo_por_umbral"]
    assert ticket_destination(judgments) == "tecnologia"
    assert ticket_priority(judgments[2]) == "normal"


def test_ticket_routine_case_can_accept_without_forcing_review() -> None:
    judgments = ticket_judgments(actionability="clarification", urgency=1.0)
    route, reasons = route_tickets(judgments, {})
    assert route == "accept"
    assert any("needs_clarification" in reason for reason in reasons)


def test_ticket_no_action_still_forces_review() -> None:
    route, reasons = route_tickets(ticket_judgments(actionability="no_action"), {})
    assert route == "review"
    assert any("actionability=no_action" in reason for reason in reasons)


def test_ticket_missing_repro_only_vetoes_high_impact() -> None:
    routine = ticket_judgments(area="tecnologia", technical_repro=0.05, urgency=1.0)
    route, _ = route_tickets(routine, {})
    assert route == "accept"
    critical = ticket_judgments(area="tecnologia", technical_repro=0.05, urgency=2.6)
    route, reasons = route_tickets(critical, {})
    assert route == "review"
    assert any("technical_repro" in reason for reason in reasons)


def test_ticket_security_and_refund_change_destination() -> None:
    judgments = ticket_judgments(security=0.9, refund=0.9)
    route, reasons = route_tickets(judgments, {})
    assert route == "review"
    assert ticket_destination(judgments) == "seguridad"
    assert any("security_legal_risk" in reason for reason in reasons)
    refund_only = ticket_judgments(refund=0.9, area="logistica", intent="solicitud")
    assert ticket_destination(refund_only) == "pagos"


def test_local_pii_forces_ticket_review() -> None:
    route, reasons = route_tickets(ticket_judgments(), {"local_pii_detected": True})
    assert route == "review"
    assert "local_pii_detected_codigo" in reasons


def test_human_signals_compose_with_their_own_cuts() -> None:
    route, reasons = route_tickets(ticket_judgments(specialist=0.55), {})
    assert route == "review"
    assert any(reason.startswith("needs_specialist.noul=") for reason in reasons)

    route, reasons = route_tickets(ticket_judgments(contradictory=0.60), {})
    assert route == "review"
    assert any(reason.startswith("is_contradictory.noul=") for reason in reasons)

    # Banda de is_ambiguous (v7): corte 0.85; 0.70 queda en incertidumbre.
    route, reasons = route_tickets(ticket_judgments(ambiguous=0.90), {})
    assert route == "review"
    assert any(reason.startswith("is_ambiguous.noul=") for reason in reasons)

    # Banda de incertidumbre (bajo el corte): deja constancia sin vetar.
    route, reasons = route_tickets(ticket_judgments(ambiguous=0.70), {})
    assert route == "accept"
    assert any("is_ambiguous.incertidumbre=" in reason for reason in reasons)


def test_sensitive_destination_requires_higher_area_confidence() -> None:
    pagos = ticket_judgments(area="pagos", intent="reclamo", area_confidence=0.70)
    assert ticket_destination(pagos) == "pagos"
    route, reasons = route_tickets(pagos, {})
    assert route == "review"
    assert any(reason.startswith("area.confidence_destino_sensible.pagos=") for reason in reasons)

    seguridad = ticket_judgments(area="seguridad", area_confidence=0.70)
    assert ticket_destination(seguridad) == "seguridad"
    route, reasons = route_tickets(seguridad, {})
    assert route == "review"
    assert any("confidence_destino_sensible.seguridad" in reason for reason in reasons)

    # Destino sensible con confidence alta se acepta.
    route, _ = route_tickets(ticket_judgments(area="pagos", intent="reclamo", area_confidence=0.90), {})
    assert route == "accept"

    # Destino no sensible mantiene piso 0.60: 0.70 sólo deja constancia.
    route, reasons = route_tickets(ticket_judgments(area="tecnologia", area_confidence=0.70), {})
    assert route == "accept"
    assert any("confidence_media" in reason for reason in reasons)


def test_urgency_uses_shared_modal_level() -> None:
    # v5: score 1.9 pasaba la ruta (1.9 < 2.0) pero la evaluación lo
    # etiquetaba "high" (round). Ambos flujos leen ahora el nivel modal.
    route, reasons = route_tickets(ticket_judgments(urgency=1.9), {})
    assert route == "review"
    assert any(reason.startswith("urgency.nivel=2") for reason in reasons)

    # Las probabilities mandan sobre el score continuo.
    judgments = ticket_judgments(urgency=1.9, urgency_probabilities={"1": 0.3, "2": 0.6})
    route, _ = route_tickets(judgments, {})
    assert route == "review"
    assert modal_level(judgments[2]) == 2
    assert ticket_priority(judgments[2]) == "high"

    # Sin probabilities cae a round(score); empate → nivel más alto (fail-closed).
    assert modal_level(Judgment("urgency", "score", 3.0, score=3.0)) == 3
    assert ticket_priority(Judgment("urgency", "score", 3.0, score=3.0)) == "critical"
    tie = Judgment("urgency", "score", 1.0, score=1.0, probabilities={"1": 0.5, "2": 0.5})
    assert modal_level(tie) == 2


def test_default_ambiguous_cut_is_085_posthoc_pending_v7() -> None:
    """Corte v7 por defecto: 0.85 (candidato post-hoc, pendiente de v7)."""
    from catalog_judge.routing import DEFAULT_THRESHOLDS, noul_band

    cut = DEFAULT_THRESHOLDS.ticket_ambiguous_noul
    assert cut == 0.85
    # La banda de incertidumbre se deriva sola: 0.65–0.85.
    assert noul_band(0.64, cut - 0.20, cut) == "no"
    assert noul_band(0.70, cut - 0.20, cut) == "incierto"
    assert noul_band(0.85, cut - 0.20, cut) == "si"
    # 0.70 cae en la banda incierta: la ruta sigue en accept.
    route, reasons = route_tickets(ticket_judgments(ambiguous=0.70), {})
    assert route == "accept"
    assert any("is_ambiguous.incertidumbre=" in reason for reason in reasons)


def test_gold_fallback_maps_expected_human_to_needs_specialist() -> None:
    from catalog_judge.tickets import gold_as_judgments

    row = {
        "expected_area": "pagos",
        "expected_intent": "consulta",
        "expected_urgency": "low",
        "expected_human": False,
        "expected_security_legal": False,
        "expected_refund": False,
        "expected_actionability": "standard_action",
        "expected_technical_repro": False,
    }
    values = {item.question_id: item for item in gold_as_judgments(row)}
    assert values["needs_specialist"].noul == 0.0
    assert values["is_ambiguous"].noul == 0.0
    assert values["is_contradictory"].noul == 0.0
    row["expected_human"] = True
    values = {item.question_id: item for item in gold_as_judgments(row)}
    assert values["needs_specialist"].noul == 1.0


def test_gold_reads_optional_human_signal_columns_when_present() -> None:
    """v7: si el CSV trae `expected_ambiguous`/`expected_contradictory`, se usan."""
    from catalog_judge.tickets import compose_expected_route, gold_as_judgments

    row = {
        "source_id": "v7-optional",
        "subject_es": "Asunto sin aclarar",
        "body_es": "No queda claro de qué pedido se trata.",
        "expected_area": "logistica",
        "expected_intent": "consulta",
        "expected_urgency": "low",
        "expected_human": True,
        "expected_ambiguous": True,
        "expected_contradictory": False,
        "expected_security_legal": False,
        "expected_refund": False,
        "expected_actionability": "standard_action",
        "expected_technical_repro": False,
    }
    values = {item.question_id: item for item in gold_as_judgments(row)}
    assert values["is_ambiguous"].noul == 1.0
    assert values["is_contradictory"].noul == 0.0
    # needs_specialist sigue materializando `expected_human` completo.
    assert values["needs_specialist"].noul == 1.0
    assert compose_expected_route(row) == "review"

    contradictory = dict(row, expected_ambiguous=False, expected_contradictory=True)
    values = {item.question_id: item for item in gold_as_judgments(contradictory)}
    assert values["is_ambiguous"].noul == 0.0
    assert values["is_contradictory"].noul == 1.0
    # Sin las columnas (lotes v4/v5/v6): fallback a 0.0 en ambas señales.
    fallback = {key: value for key, value in row.items() if key not in {"expected_ambiguous", "expected_contradictory"}}
    values = {item.question_id: item for item in gold_as_judgments(fallback)}
    assert values["is_ambiguous"].noul == 0.0
    assert values["is_contradictory"].noul == 0.0


def test_compose_expected_route_uses_the_same_function_as_prediction() -> None:
    from catalog_judge.routing import route_tickets
    from catalog_judge.tickets import compose_expected_route, gold_as_judgments

    row = {
        "source_id": "synthetic-route",
        "subject_es": "Consulta de factura",
        "body_es": "No entiendo un concepto del comprobante.",
        "expected_area": "pagos",
        "expected_intent": "consulta",
        "expected_urgency": "low",
        "expected_human": False,
        "expected_security_legal": False,
        "expected_refund": False,
        "expected_actionability": "standard_action",
        "expected_technical_repro": False,
    }
    assert compose_expected_route(row) == "accept"
    composed, _ = route_tickets(gold_as_judgments(row), {"local_pii_detected": False})
    assert composed == "accept"
    row["expected_human"] = True
    assert compose_expected_route(row) == "review"
    row["expected_human"] = False
    row["expected_actionability"] = "clarification"
    assert compose_expected_route(row) == "accept"
    row["expected_actionability"] = "no_action"
    assert compose_expected_route(row) == "review"
    include = classify_retail_policy({
        "series_id": "ok",
        "store_nbr": 1,
        "family": "GROCERY I",
        "avg_sales": 400.0,
        "sales_cv": 0.4,
        "active_day_share": 0.95,
        "promo_share": 0.1,
        "recent_vs_previous_ratio": 1.0,
    })
    assert include["series_decision"] == "include"
    assert include["route"] == "accept"
    drop = classify_retail_policy({
        "series_id": "drop",
        "store_nbr": 1,
        "family": "GROCERY I",
        "avg_sales": 400.0,
        "sales_cv": 0.4,
        "active_day_share": 0.95,
        "promo_share": 0.1,
        "recent_vs_previous_ratio": 0.5,
    })
    assert drop["series_decision"] == "review"
    assert drop["route"] == "review"
    assert "demand_drop_alert_proxy_codigo" in drop["reasons"]
    empty = classify_retail_policy({
        "series_id": "empty",
        "store_nbr": 1,
        "family": "GROCERY I",
        "avg_sales": 0.0,
        "sales_cv": 0.0,
        "active_day_share": 0.05,
        "promo_share": 0.0,
        "recent_vs_previous_ratio": 1.0,
    })
    assert empty["series_decision"] == "exclude"
    assert empty["route"] == "block"
