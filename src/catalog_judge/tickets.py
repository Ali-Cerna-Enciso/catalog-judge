"""State y gold compuesto para tickets públicos curados en español."""

from __future__ import annotations

from typing import Any

from .contracts import Judgment, Route
from .privacy import contains_pii, redact_text, safe_preview
from .prompts import TICKET_QUESTION_IDS
from .routing import DEFAULT_THRESHOLDS, RoutingThresholds, route_tickets

URGENCY_TO_SCORE = {"low": 0.0, "medium": 1.0, "high": 2.0, "critical": 3.0}
ACTIONABILITY_LABELS = ("no_action", "clarification", "standard_action", "immediate_action")

# KB operativa: qué significa cada nivel de `actionability` para este
# equipo (qué se ejecuta sin pedir más datos). Solo texto operativo:
# sin gold, `expected_*` ni cortes de política.
TEAM_POLICY: dict[str, str] = {
    "scope": "Qué hace este equipo de soporte sin pedir más datos.",
    "standard_action": (
        "Se ejecuta sin más datos cuando el ticket trae tarea y objeto identificables: "
        "número de pedido o cuenta, producto o servicio nombrado, y acción concreta "
        "(cotización, cambio de datos, seguimiento de caso, estado de un reembolso)."
    ),
    "clarification": (
        "Sólo se piden datos cuando falta el objeto concreto: sin número de pedido, "
        "de cuenta o de ítem no hay tarea que ejecutar."
    ),
    "immediate_action": (
        "Fraude, acceso no autorizado o caída de servicio: cola de atención inmediata, "
        "sin espera."
    ),
    "no_action": "No se abre tarea: agradecimiento o texto sin acción que ejecutar.",
}


def ticket_text(row: dict[str, Any]) -> str:
    subject = str(row.get("subject_es", "")).strip()
    body = str(row.get("body_es", "")).strip()
    if subject and body:
        return f"{subject}\n{body}"
    return subject or body or str(row.get("texto", "")).strip()


def build_ticket_state(row: dict[str, Any]) -> dict[str, Any]:
    """State: ticket redactado + KB `team_policy`. El flag PII queda en computed, no en Jev."""
    subject = redact_text(str(row.get("subject_es", "")).strip())
    body = redact_text(str(row.get("body_es", "")).strip() or str(row.get("texto", "")).strip())
    return {
        "ticket": {
            "subject": subject,
            "body": body,
        },
        "team_policy": TEAM_POLICY,
    }


def gold_as_judgments(row: dict[str, Any]) -> list[Judgment]:
    """Materializa el gold como juicios de confianza 1.0 para componer la ruta.

    `expected_human` es el gold de rúbrica; `expected_ambiguous` y
    `expected_contradictory` son opcionales y, si faltan, valen 0.0 sin
    alterar el `expected_route` congelado. `needs_specialist` comparte
    `expected_human` (decisión de diseño).
    """
    area = str(row.get("expected_area") or "otro")
    intent = str(row.get("expected_intent") or "otro")
    urgency = URGENCY_TO_SCORE.get(str(row.get("expected_urgency") or "low"), 0.0)
    action = str(row.get("expected_actionability") or "clarification")
    if action not in ACTIONABILITY_LABELS:
        action = "clarification"
    specialist = 1.0 if row.get("expected_human") else 0.0
    ambiguous = 1.0 if row.get("expected_ambiguous") else 0.0
    contradictory = 1.0 if row.get("expected_contradictory") else 0.0
    security = 1.0 if row.get("expected_security_legal") else 0.0
    refund = 1.0 if row.get("expected_refund") else 0.0
    repro = 1.0 if row.get("expected_technical_repro") else 0.0
    values = {
        "area": Judgment("area", "choice", area, confidence=1.0, choice=area),
        "intent": Judgment("intent", "choice", intent, confidence=1.0, choice=intent),
        "urgency": Judgment("urgency", "score", urgency, confidence=1.0, score=urgency),
        "is_ambiguous": Judgment("is_ambiguous", "noul", ambiguous, noul=ambiguous),
        "is_contradictory": Judgment("is_contradictory", "noul", contradictory, noul=contradictory),
        "needs_specialist": Judgment("needs_specialist", "noul", specialist, noul=specialist),
        "security_legal_risk": Judgment("security_legal_risk", "noul", security, noul=security),
        "refund_or_replacement": Judgment("refund_or_replacement", "noul", refund, noul=refund),
        "actionability": Judgment("actionability", "choice", action, confidence=1.0, choice=action),
        "technical_repro": Judgment("technical_repro", "noul", repro, noul=repro),
    }
    return [values[qid] for qid in TICKET_QUESTION_IDS]


def compose_expected_route(
    row: dict[str, Any],
    thresholds: RoutingThresholds = DEFAULT_THRESHOLDS,
) -> Route:
    """La ruta gold es la misma función que la predicción, aplicada al gold."""
    computed = {"local_pii_detected": contains_pii(ticket_text(row))}
    route, _ = route_tickets(gold_as_judgments(row), computed, thresholds)
    return route


def expected_fields(row: dict[str, Any]) -> dict[str, Any]:
    payload = {
        key: row[key]
        for key in (
            "expected_area",
            "expected_intent",
            "expected_urgency",
            "expected_human",
            "expected_ambiguous",
            "expected_contradictory",
            "expected_security_legal",
            "expected_refund",
            "expected_actionability",
            "expected_technical_repro",
            "expected_route",
        )
        if key in row
    }
    if "expected_area" in payload:
        payload["expected_route"] = compose_expected_route(row)
    return payload


def ticket_row_id(row: dict[str, Any]) -> str:
    return redact_text(str(row["source_id"]))


def ticket_preview(row: dict[str, Any]) -> str:
    return safe_preview(ticket_text(row), 240)
