"""Adaptadores de backend: TypeSafe/Jev real y mock determinista.

El cliente real se importa de forma perezosa para que los tests offline puedan
usar el mismo harness sin key ni red.
"""

from __future__ import annotations

import inspect
import math
import os
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Protocol, cast

from .config import DEFAULT_MODEL, Settings
from .contracts import Judgment, JudgmentKind
from .privacy import redact_state


class BackendError(RuntimeError):
    """Error sanitizado que no contiene key, body remoto ni texto de entrada."""

    def __init__(self, code: str, message: str, *, status: int | None = None, request_id: str | None = None):
        super().__init__(message)
        self.code = code
        self.status = status
        self.request_id = request_id


class ContractError(RuntimeError):
    """La respuesta no cumple el contrato de preguntas/valores."""


class JudgmentBackend(Protocol):
    def classify(self, state: dict[str, Any], questions: dict[str, Any], hints: dict[str, Any] | None = None) -> Any:
        ...


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "si", "sí", "active"}


_SDK_LOG_LOCK = threading.Lock()


@contextmanager
def _temporary_sdk_log_level(level: str):
    """Configura el logger sólo durante el import/uso del SDK actual."""
    with _SDK_LOG_LOCK:
        previous = os.environ.get("TYPESAFE_LOG_LEVEL")
        if level:
            os.environ["TYPESAFE_LOG_LEVEL"] = level
        else:
            os.environ.pop("TYPESAFE_LOG_LEVEL", None)
        try:
            yield
        finally:
            if previous is None:
                os.environ.pop("TYPESAFE_LOG_LEVEL", None)
            else:
                os.environ["TYPESAFE_LOG_LEVEL"] = previous


class JevBackend:
    """Wrapper mínimo sobre ``typesafe_sdk.TypeSafeClient``.

    Un objeto nuevo por llamada evita compartir clientes HTTP entre workers y
    mantiene explícita la política de una llamada por fila.
    """

    def __init__(self, settings: Settings, allow_remote: bool):
        if not allow_remote:
            raise BackendError("remote_consent_required", "live requiere consentimiento explícito")
        if not settings.has_api_key:
            raise BackendError("missing_api_key", "falta TYPESAFE_API_KEY para modo live")
        if settings.model != DEFAULT_MODEL:
            raise BackendError("model_not_pinned", f"live requiere el modelo {DEFAULT_MODEL}")
        if settings.log_level == "debug":
            raise BackendError("unsafe_log_level", "debug puede registrar bodies; usa warning o error")
        self.settings = settings
        self.allow_remote = allow_remote

    @contextmanager
    def sdk_log_context(self):
        """Contexto de logging para construir preguntas antes del worker."""
        with _temporary_sdk_log_level(self.settings.log_level):
            yield

    def classify(self, state: dict[str, Any], questions: dict[str, Any], hints: dict[str, Any] | None = None) -> Any:
        del hints  # El backend real nunca consume gold ni hints del mock.
        safe_state = redact_state(state)
        try:
            sdk = self._load_sdk()
        except ImportError as exc:  # pragma: no cover - depende del entorno
            raise BackendError("sdk_missing", "typesafe-sdk no está instalado") from exc
        return self._classify_with_sdk(safe_state, questions, sdk)

    def _load_sdk(self) -> tuple[Any, Any, Any, Any]:
        """Importa el SDK bajo el nivel de log, sin mantener el lock durante HTTP."""
        with self.sdk_log_context():
            from typesafe_sdk import RetryPolicy, TypeSafeAPIError, TypeSafeAPITimeoutError, TypeSafeClient

        return RetryPolicy, TypeSafeAPIError, TypeSafeAPITimeoutError, TypeSafeClient

    def _classify_with_sdk(self, safe_state: dict[str, Any], questions: dict[str, Any], sdk: tuple[Any, Any, Any, Any]) -> Any:
        RetryPolicy, TypeSafeAPIError, TypeSafeAPITimeoutError, TypeSafeClient = sdk
        retry = RetryPolicy(max_retries=2, timeout=self.settings.timeout_seconds)
        try:
            with TypeSafeClient(
                api_key=self.settings.api_key,
                model=self.settings.model,
                base_url=self.settings.base_url,
                timeout=self.settings.timeout_seconds,
                retry=retry,
            ) as client:
                return client.system_one(safe_state, questions, model=self.settings.model)
        except TypeSafeAPIError as exc:
            status = getattr(exc, "status", None)
            status_code = int(status) if isinstance(status, int) else None
            code = (
                {
                    401: "unauthorized",
                    429: "rate_limited",
                    408: "timeout",
                }.get(status_code, f"api_{status_code}")
                if status_code is not None
                else "api_error"
            )
            request_id = getattr(exc, "request_id", None)
            if status_code == 401:
                message = "TypeSafe rechazó la autenticación (401); revise la key sin imprimirla"
            elif status_code == 429:
                message = "TypeSafe aplicó rate limit (429); la fila queda en error/revisión"
            else:
                message = f"TypeSafe rechazó la solicitud (HTTP {status_code or 'desconocido'})"
            raise BackendError(code, message, status=status_code, request_id=request_id) from None
        except TypeSafeAPITimeoutError:
            raise BackendError("timeout", "la solicitud a TypeSafe agotó el timeout") from None
        except TimeoutError:
            raise BackendError("timeout", "la solicitud a TypeSafe agotó el timeout") from None
        except ConnectionError:
            raise BackendError("connection", "no se pudo conectar con TypeSafe") from None
        except Exception as exc:
            # No persistimos str(exc): algunas versiones incluyen body remoto.
            raise BackendError("backend_error", f"fallo inesperado del backend ({type(exc).__name__})") from None


@dataclass
class MockAnswer:
    type: str
    noul: float | None = None
    choice: str | None = None
    score: float | None = None
    confidence: float | None = None
    probabilities: dict[str, float] | None = None


class MockResponse:
    def __init__(self, answers: dict[str, MockAnswer], request_id: str):
        self.answers = answers
        self.model = "mock-deterministic"
        self.request_id = request_id


class DeterministicMockJev:
    """Mock heurístico y reproducible; nunca lee ``expected_*`` ni gold.

    Sirve para ejercitar la interfaz y los cortes, no para afirmar la calidad
    de Jev ni para producir una métrica de producción.
    """

    def __init__(self) -> None:
        self.call_count = 0
        self.question_counts: list[int] = []

    def classify(self, state: dict[str, Any], questions: dict[str, Any], hints: dict[str, Any] | None = None) -> MockResponse:
        del hints  # El mock no consume gold ni expected_*.
        self.call_count += 1
        self.question_counts.append(len(questions))
        if state.get("domain") == "retail":
            answers = self._retail_answers(state, questions)
        else:
            answers = self._ticket_answers(state, questions)
        return MockResponse(answers, f"mock-{self.call_count:08d}")

    @staticmethod
    def _type(question: Any) -> str:
        if isinstance(question, dict):
            return str(question.get("type", ""))
        return str(getattr(question, "type", ""))

    @staticmethod
    def _options(question: Any) -> list[str]:
        return list(getattr(question, "criteria", {}) or {})

    @staticmethod
    def _choice(value: str, confidence: float, question: Any) -> MockAnswer:
        options = DeterministicMockJev._options(question)
        probabilities = {option: (1.0 - confidence) / max(1, len(options) - 1) for option in options if option != value}
        probabilities[value] = confidence
        return MockAnswer(type="choice", choice=value, confidence=confidence, probabilities=probabilities)

    @staticmethod
    def _score(value: float, confidence: float, levels: int) -> MockAnswer:
        probabilities = {
            str(index): confidence if int(round(value)) == index else (1.0 - confidence) / max(1, levels - 1)
            for index in range(levels)
        }
        return MockAnswer(type="score", score=float(value), confidence=confidence, probabilities=probabilities)

    @staticmethod
    def _noul(value: float) -> MockAnswer:
        return MockAnswer(type="noul", noul=value)

    def _retail_answers(self, state: dict[str, Any], questions: dict[str, Any]) -> dict[str, MockAnswer]:
        features = state.get("demand_features", {})
        avg = float(features.get("avg_sales", 0) or 0)
        cv = float(features.get("sales_cv", 0) or 0)
        active = float(features.get("active_day_share", 0) or 0)
        promo = float(features.get("promo_share", 0) or 0)
        ratio_value = features.get("recent_vs_previous_ratio")
        ratio = None if ratio_value in (None, "") else float(ratio_value)
        drop = bool(state.get("demand_drop_alert", ratio is not None and ratio < 0.75 and avg > 0))
        candidate = bool(state.get("replenishment_candidate", ratio is not None and ratio >= 1.10 and active >= 0.35 and avg > 0))
        bands = state.get("demand_bands") or {}
        volume = str(bands.get("volume", ""))
        trend = str(bands.get("trend", ""))
        presence = str(bands.get("presence", ""))
        volatility = str(bands.get("volatility", ""))
        promo_band = str(bands.get("promo", ""))
        if bands and volume and trend and presence and volatility:
            # El mock lee bandas nombradas como Jev; los cortes de gold
            # viven en prepare_public_fixtures.
            risk = volatility in {"alta", "extrema"} or presence in {"muy_baja", "baja"} or promo_band == "alta"
            exception = trend in {"caida", "insuficiente"} or volatility == "extrema" or presence == "muy_baja"
            if volume == "muy_baja" and presence == "muy_baja":
                decision, confidence = "exclude", 0.82
            elif trend in {"caida", "insuficiente"} or risk or exception:
                decision, confidence = "review", 0.66
            else:
                decision, confidence = "include", 0.84 if candidate else 0.80
            handling = 0.84 if risk else (0.45 if volatility == "alta" or presence == "media" else 0.12)
            need_exception = 0.88 if exception else (0.45 if trend == "estable" and volatility == "alta" else 0.14)
        else:
            # Sin bandas (estados viejos o sintéticos): heurística numérica
            # conservadora.
            risk = cv >= 1.15 or active < 0.20 or promo >= 0.65
            exception = drop or cv >= 1.80 or active < 0.10
            if avg <= 0 or active < 0.08:
                decision, confidence = "exclude", 0.82
            elif drop or risk or exception:
                decision, confidence = "review", 0.66
            else:
                decision, confidence = "include", 0.84 if candidate else 0.80
            handling = 0.84 if risk else 0.12
            need_exception = 0.88 if exception else 0.14
        return {
            "series_decision": self._choice(decision, confidence, questions["series_decision"]),
            "handling_risk": self._noul(handling),
            "exception_needed": self._noul(need_exception),
        }

    def _ticket_answers(self, state: dict[str, Any], questions: dict[str, Any]) -> dict[str, MockAnswer]:
        raw_ticket = state.get("ticket")
        ticket = raw_ticket if isinstance(raw_ticket, dict) else {}
        text = f"{ticket.get('subject', '')} {ticket.get('body', '')} {state.get('texto', '')}".lower()
        security = any(word in text for word in ("acceso no autorizado", "acceso indebido", "credencial", "fraude", "privacidad", "seguridad", "legal", "dato sensible"))
        refund = any(word in text for word in ("reembolso", "devolución", "cambio", "reemplazo", "devolver"))
        technical = any(word in text for word in ("error", "fallo", "falla", "pantalla", "mensaje", "incidente", "integración", "sistema", "aplicación", "no responde"))
        area = "otro"
        if security:
            area = "seguridad"
        elif refund or any(word in text for word in ("factura", "cobro", "pago")):
            area = "pagos"
        elif any(word in text for word in ("entrega", "pedido", "envío", "paquete", "almacén")):
            area = "logistica"
        elif any(word in text for word in ("contratación", "personas", "rrhh", "incorporación")):
            area = "rrhh"
        elif any(word in text for word in ("cotización", "propuesta", "presupuesto", "precio")):
            area = "ventas"
        elif technical:
            area = "tecnologia"
        elif any(word in text for word in ("atención", "servicio", "cliente", "consulta")):
            area = "atencion_cliente"
        if any(word in text for word in ("reembolso", "devolución", "cambio", "reemplazo")) and any(word in text for word in ("problema", "reclamo", "insatisf")):
            intent = "reclamo"
        elif any(word in text for word in ("error", "falla", "problema", "incidente", "no responde")):
            intent = "incidencia"
        elif any(word in text for word in ("queja", "reclamo", "insatisf", "molest")):
            intent = "reclamo"
        elif any(word in text for word in ("sugerencia", "sugiero", "mejora", "opinión")):
            intent = "retroalimentacion"
        elif any(word in text for word in ("consulta", "pregunta", "información", "explicar")):
            intent = "consulta"
        else:
            intent = "solicitud"
        if any(word in text for word in ("no puede esperar", "inmediato", "urgente", "crítico", "bloquea", "caída general")):
            urgency, urgency_confidence = 3.0, 0.90
        elif any(word in text for word in ("hoy", "antes de", "pronto", "rápido")):
            urgency, urgency_confidence = 2.0, 0.84
        elif any(word in text for word in ("cuando puedan", "sin urgencia", "próxima revisión", "no hay prisa")):
            urgency, urgency_confidence = 0.0, 0.78
        else:
            urgency, urgency_confidence = 1.0, 0.70
        ambiguous = any(word in text for word in ("no encuentro", "no está claro", "necesito aclaración", "persona", "confirmar", "ambig"))
        contradictory = any(word in text for word in ("contradic", "instrucciones opuestas", "dice lo contrario"))
        # El veto humano se compone así (ámbito del equipo, no del gold):
        # la ambigüedad aporta su propia señal; specialist cubre el resto.
        specialist = security or area == "otro" or urgency >= 3
        action_label = "clarification" if ambiguous else ("immediate_action" if security or urgency >= 3 else "standard_action")
        technical_repro = 0.86 if technical and any(word in text for word in ("pasos", "error", "mensaje", "pantalla", "reproduc", "bitácora")) else 0.10
        return {
            "area": self._choice(area, 0.90 if area != "otro" else 0.48, questions["area"]),
            "intent": self._choice(intent, 0.84 if intent != "otro" else 0.48, questions["intent"]),
            "urgency": self._score(urgency, urgency_confidence, 4),
            "is_ambiguous": self._noul(0.88 if ambiguous else 0.14),
            "is_contradictory": self._noul(0.88 if contradictory else 0.14),
            "needs_specialist": self._noul(0.88 if specialist else 0.14),
            "security_legal_risk": self._noul(0.91 if security else 0.08),
            "refund_or_replacement": self._noul(0.90 if refund else 0.08),
            "actionability": self._choice(action_label, 0.82, questions["actionability"]),
            "technical_repro": self._noul(technical_repro),
        }


def call_backend(backend: JudgmentBackend, state: dict[str, Any], questions: dict[str, Any], hints: dict[str, Any] | None) -> Any:
    """Llama al backend admitiendo doubles de test con o sin ``hints``."""

    method = backend.classify
    try:
        signature = inspect.signature(method)
        accepts_hints = "hints" in signature.parameters or any(
            parameter.kind == parameter.VAR_KEYWORD for parameter in signature.parameters.values()
        )
    except (TypeError, ValueError):
        accepts_hints = True
    if accepts_hints:
        return method(state, questions, hints=hints)
    return method(state, questions)


def _get(answer: Any, name: str, default: Any = None) -> Any:
    if isinstance(answer, dict):
        return answer.get(name, default)
    return getattr(answer, name, default)


def normalize_response(response: Any, questions: dict[str, Any], expected_ids: tuple[str, ...]) -> list[Judgment]:
    """Valida forma, cardinalidad y rangos; nunca rellena una respuesta faltante."""

    answers = _get(response, "answers")
    if not isinstance(answers, dict):
        raise ContractError("respuesta sin mapa answers")
    missing = [qid for qid in expected_ids if qid not in answers]
    if missing:
        raise ContractError(f"faltan respuestas: {','.join(missing)}")
    normalized: list[Judgment] = []
    for qid in expected_ids:
        answer = answers[qid]
        question = questions[qid]
        expected_kind = _get(question, "type")
        actual_kind = _get(answer, "type")
        if actual_kind is not None and str(actual_kind) != str(expected_kind):
            raise ContractError(f"tipo inesperado en {qid}")
        kind = cast(JudgmentKind, str(expected_kind))
        noul = _get(answer, "noul")
        choice = _get(answer, "choice")
        score = _get(answer, "score")
        confidence = _get(answer, "confidence")
        probabilities = _get(answer, "probabilities", {}) or {}
        probabilities = {str(key): float(value) for key, value in dict(probabilities).items()}
        if kind == "noul":
            if not isinstance(noul, (int, float)) or not math.isfinite(float(noul)) or not 0 <= float(noul) <= 1:
                raise ContractError(f"Noul inválido en {qid}")
            confidence = None
            value: float | str = float(noul)
        elif kind == "score":
            if not isinstance(score, (int, float)) or not math.isfinite(float(score)):
                raise ContractError(f"Score inválido en {qid}")
            criteria = _get(question, "criteria", []) or []
            maximum = max(0, len(criteria) - 1)
            if float(score) < 0 or float(score) > maximum:
                raise ContractError(f"Score fuera de rango en {qid}")
            value = float(score)
        else:
            if not isinstance(choice, str):
                raise ContractError(f"Choice inválido en {qid}")
            criteria = _get(question, "criteria", {}) or {}
            if criteria and choice not in criteria:
                raise ContractError(f"opción fuera de contrato en {qid}")
            value = choice
        if confidence is not None:
            try:
                confidence = float(confidence)
            except (TypeError, ValueError) as exc:
                raise ContractError(f"confidence inválida en {qid}") from exc
            if not math.isfinite(confidence) or not 0 <= confidence <= 1:
                raise ContractError(f"confidence fuera de rango en {qid}")
        if any(not math.isfinite(value) or value < 0 or value > 1 for value in probabilities.values()):
            raise ContractError(f"probabilidades inválidas en {qid}")
        normalized.append(Judgment(
            question_id=qid,
            kind=kind,
            value=value,
            confidence=confidence,
            noul=float(noul) if kind == "noul" and noul is not None else None,
            choice=str(choice) if kind == "choice" else None,
            score=float(score) if kind == "score" and score is not None else None,
            probabilities=probabilities,
        ))
    if len(normalized) != len(expected_ids):
        raise ContractError("cardinalidad incorrecta")
    return normalized


def backend_request_id(response: Any) -> str | None:
    value = _get(response, "request_id")
    return str(value) if value else None
