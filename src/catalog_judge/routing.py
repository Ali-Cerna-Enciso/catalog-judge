"""Umbrales y rutas fail-closed.

Retail usa su propia política de demanda (``retail.py``).

Tickets (protocolo v7): `accept` = clasificación aceptada para derivar.
La misma función compone la predicción y el gold (`compose_expected_route`).

- Choice: piso 0.60, media hasta 0.75 deja constancia sin vetar.
  Destinos sensibles (`SENSITIVE_DESTINATIONS`) exigen 0.85 en `area`.
- Noul humanos: `is_ambiguous` corte 0.85 (fijado en v7 a partir del
  diagnóstico de v6 y congelado antes del live), `is_contradictory` y
  `needs_specialist` 0.50; la ruta compone con OR y nombra la señal
  que dispara.
- `actionability` es Choice: solo `no_action` veta.
- `urgency` se lee por nivel modal (`modal_level`): nivel >= 2 veta.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import Judgment, Route
from .prompts import TICKET_QUESTION_IDS


@dataclass(frozen=True)
class RoutingThresholds:
    # Retail: cada señal tiene su propio corte.
    retail_choice_review: float = 0.50
    retail_choice_accept: float = 0.75
    retail_handling_noul: float = 0.65
    retail_exception_noul: float = 0.70
    # Tickets: cada tipo de señal tiene su propio corte.
    ticket_choice_review: float = 0.60
    ticket_choice_accept: float = 0.75
    ticket_choice_sensitive_accept: float = 0.85
    ticket_specialist_noul: float = 0.50
    ticket_contradictory_noul: float = 0.50
    # Fijado en v7 a partir del diagnóstico de v6 y congelado antes del live.
    ticket_ambiguous_noul: float = 0.85
    ticket_security_noul: float = 0.65
    ticket_refund_noul: float = 0.50
    ticket_urgency_high: float = 2.00
    ticket_actionability_review: float = 1.00
    ticket_technical_repro_review: float = 0.35


DEFAULT_THRESHOLDS = RoutingThresholds()

# Destinos sensibles: exigen confidence alta en `area` para aceptar.
SENSITIVE_DESTINATIONS = frozenset({"seguridad", "pagos"})

# Las tres señales humanas y sus cortes; ruta y evaluación comparten
# la lista para leer igual en ambos lados.
HUMAN_SIGNAL_CUTS: tuple[tuple[str, str], ...] = (
    ("is_ambiguous", "ticket_ambiguous_noul"),
    ("is_contradictory", "ticket_contradictory_noul"),
    ("needs_specialist", "ticket_specialist_noul"),
)


def _by_id(judgments: list[Judgment]) -> dict[str, Judgment]:
    return {item.question_id: item for item in judgments}


def normalized_score(answer: Judgment, levels: int) -> float | None:
    """Score 0-1 normalizado por el nivel máximo; evita que una escala domine."""
    if answer.score is None or levels < 2:
        return None
    return max(0.0, min(1.0, float(answer.score) / float(levels - 1)))


def modal_level(answer: Judgment, levels: int = 4) -> int | None:
    """Nivel modal de un Score: argmax de ``probabilities``; sin probabilities
    cae a ``int(round(score))`` clampado. Empate → el nivel más alto (fail-closed).

    Es el criterio compartido entre ruta, prioridad y etiqueta de evaluación.
    """
    if answer.probabilities:
        candidates: dict[int, float] = {}
        for key, probability in answer.probabilities.items():
            try:
                index = int(key)
            except (TypeError, ValueError):
                continue
            if 0 <= index < levels:
                candidates[index] = float(probability)
        if candidates:
            return max(sorted(candidates), key=lambda index: (candidates[index], index))
    if answer.score is None:
        return None
    return max(0, min(levels - 1, int(round(answer.score))))


def noul_band(value: float, low: float, high: float) -> str:
    """Banda de un Noul: `no` bajo el corte bajo, `incierto` en medio, `si` arriba."""
    if value < low:
        return "no"
    if value < high:
        return "incierto"
    return "si"


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)


def ticket_destination(judgments: list[Judgment], thresholds: RoutingThresholds = DEFAULT_THRESHOLDS) -> str:
    """Calcula el destino en código; la categoría nunca decide sola."""
    values = _by_id(judgments)
    area = values.get("area")
    intent = values.get("intent")
    security = values.get("security_legal_risk")
    refund = values.get("refund_or_replacement")
    if security is not None and (security.noul or 0) >= thresholds.ticket_security_noul:
        return "seguridad"
    if refund is not None and (refund.noul or 0) >= thresholds.ticket_refund_noul:
        return "pagos"
    if intent is not None and intent.choice in {"reclamo", "solicitud"} and area is not None and area.choice == "logistica":
        return "logistica"
    return area.choice if area is not None and area.choice else "otro"


def ticket_priority(urgency: Judgment) -> str:
    level = modal_level(urgency, 4)
    if level is None or level <= 0:
        return "low"
    if level == 1:
        return "normal"
    if level == 2:
        return "high"
    return "critical"


def route_tickets(
    judgments: list[Judgment],
    computed: dict[str, Any] | None = None,
    thresholds: RoutingThresholds = DEFAULT_THRESHOLDS,
) -> tuple[Route, list[str]]:
    values = _by_id(judgments)
    if not set(TICKET_QUESTION_IDS).issubset(values):
        return "error", ["contrato_incompleto"]
    area = values["area"]
    intent = values["intent"]
    urgency = values["urgency"]
    security = values["security_legal_risk"].noul
    refund = values["refund_or_replacement"].noul
    action = values["actionability"].choice
    technical_repro = values["technical_repro"].noul
    human_signals: dict[str, float] = {}
    for qid, _ in HUMAN_SIGNAL_CUTS:
        signal = values[qid].noul
        if signal is None:
            return "error", ["noul_ausente"]
        human_signals[qid] = signal
    if area.choice is None or intent.choice is None or urgency.score is None or action is None:
        return "error", ["respuesta_incompleta"]
    if security is None or refund is None or technical_repro is None:
        return "error", ["noul_ausente"]
    urgency_level = modal_level(urgency, 4)
    if urgency_level is None:
        return "error", ["respuesta_incompleta"]

    reasons: list[str] = []
    review = False
    destination = ticket_destination(judgments, thresholds)
    sensitive = destination in SENSITIVE_DESTINATIONS
    for answer, label in ((area, "area"), (intent, "intent")):
        confidence = answer.confidence
        if label == "area" and sensitive:
            # Destino sensible: `area` es quien clasifica la cola, así que
            # exige confidence alta para aceptar sin revisión.
            if confidence is None or confidence < thresholds.ticket_choice_sensitive_accept:
                review = True
                reasons.append(f"area.confidence_destino_sensible.{destination}={_fmt(confidence or 0)}")
            continue
        if confidence is None or confidence < thresholds.ticket_choice_review:
            review = True
            reasons.append(f"{label}.confidence_bajo={_fmt(confidence or 0)}")
        elif confidence < thresholds.ticket_choice_accept:
            reasons.append(f"{label}.confidence_media={_fmt(confidence)}")
    if area.choice == "otro" or intent.choice == "otro":
        review = True
        reasons.append("area_o_intent_otro")
    for qid, attr in HUMAN_SIGNAL_CUTS:
        value = human_signals[qid]
        cut = getattr(thresholds, attr)
        band = noul_band(value, cut - 0.20, cut)
        if band == "si":
            review = True
            reasons.append(f"{qid}.noul={_fmt(value)}")
        elif band == "incierto":
            reasons.append(f"{qid}.incertidumbre={_fmt(value)}")
    if security >= thresholds.ticket_security_noul:
        review = True
        reasons.append(f"security_legal_risk.noul={_fmt(security)}")
    if refund >= thresholds.ticket_refund_noul:
        reasons.append(f"refund_or_replacement.noul={_fmt(refund)}")
    if action == "no_action":
        review = True
        reasons.append("actionability=no_action")
    elif action == "clarification":
        reasons.append("needs_clarification")
    if urgency_level >= thresholds.ticket_urgency_high:
        review = True
        reasons.append(f"urgency.nivel={_fmt(urgency_level)}")
    if (
        area.choice == "tecnologia"
        and urgency_level >= thresholds.ticket_urgency_high
        and technical_repro < thresholds.ticket_technical_repro_review
    ):
        # Sin evidencia reproducible sólo se veta cuando el impacto es alto;
        # en rutina queda como detalle informativo en `computed`.
        review = True
        reasons.append(f"technical_repro.noul={_fmt(technical_repro)}")
    if computed and computed.get("local_pii_detected"):
        review = True
        reasons.append("local_pii_detected_codigo")
    return ("review" if review else "accept"), reasons or ["ruteo_por_umbral"]
