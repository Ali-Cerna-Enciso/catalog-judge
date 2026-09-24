"""Contratos de salida del harness.

Los contratos son deliberados y pequeños: una fila produce un conjunto de
``Judgment`` y el código, no el modelo, decide la ruta operativa.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, cast

JudgmentKind = Literal["noul", "choice", "score"]
Route = Literal["accept", "review", "block", "error"]


@dataclass(frozen=True)
class Judgment:
    """Respuesta normalizada de una sola pregunta atómica."""

    question_id: str
    kind: JudgmentKind
    value: float | str
    confidence: float | None = None
    noul: float | None = None
    choice: str | None = None
    score: float | None = None
    probabilities: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "question_id": self.question_id,
            "kind": self.kind,
            "value": self.value,
        }
        if self.confidence is not None:
            payload["confidence"] = self.confidence
        if self.noul is not None:
            payload["noul"] = self.noul
        if self.choice is not None:
            payload["choice"] = self.choice
        if self.score is not None:
            payload["score"] = self.score
        if self.probabilities:
            payload["probabilities"] = self.probabilities
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Judgment:
        kind = cast(JudgmentKind, payload.get("kind"))
        if kind not in {"noul", "choice", "score"}:
            raise ValueError(f"kind inválido: {kind!r}")
        value = cast(float | str, payload.get("value"))
        if kind == "noul" and not isinstance(value, (int, float)):
            raise ValueError("Noul necesita un valor numérico")
        if kind == "score" and not isinstance(value, (int, float)):
            raise ValueError("Score necesita un valor numérico")
        if kind == "choice" and not isinstance(value, str):
            raise ValueError("Choice necesita un valor textual")
        return cls(
            question_id=str(payload["question_id"]),
            kind=kind,
            value=value,
            confidence=_optional_float(payload.get("confidence")),
            noul=_optional_float(payload.get("noul")),
            choice=payload.get("choice"),
            score=_optional_float(payload.get("score")),
            probabilities={
                str(k): float(v) for k, v in (payload.get("probabilities") or {}).items()
            },
        )


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


@dataclass
class RowResult:
    """Resultado auditable de una fila, sin depender de la UI."""

    domain: Literal["retail", "tickets"]
    row_id: str
    route: Route
    status: Literal["ok", "error"]
    reasons: list[str] = field(default_factory=list)
    judgments: list[Judgment] = field(default_factory=list)
    computed: dict[str, Any] = field(default_factory=dict)
    expected: dict[str, Any] = field(default_factory=dict)
    redacted_text: str | None = None
    latency_ms: float | None = None
    request_id: str | None = None
    error_code: str | None = None
    mock: bool = False
    backend: Literal["jev", "code", "mock"] = "jev"

    def judgment_map(self) -> dict[str, Judgment]:
        return {judgment.question_id: judgment for judgment in self.judgments}

    def to_dict(self, include_judgments: bool = True, include_text: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "domain": self.domain,
            "row_id": self.row_id,
            "route": self.route,
            "status": self.status,
            "reasons": self.reasons,
            "computed": self.computed,
            "expected": self.expected,
            "latency_ms": self.latency_ms,
            "request_id": self.request_id,
            "error_code": self.error_code,
            "mock": self.mock,
            "backend": self.backend,
        }
        if include_judgments:
            payload["judgments"] = [judgment.to_dict() for judgment in self.judgments]
        if include_text and self.redacted_text is not None:
            payload["redacted_text"] = self.redacted_text
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> RowResult:
        domain = payload.get("domain")
        if domain not in {"retail", "tickets"}:
            raise ValueError("dominio inválido")
        route = payload.get("route")
        if route not in {"accept", "review", "block", "error"}:
            raise ValueError("ruta inválida")
        status = payload.get("status", "error")
        if status not in {"ok", "error"}:
            raise ValueError("status inválido")
        return cls(
            domain=domain,
            row_id=str(payload.get("row_id", "")),
            route=route,
            status=status,
            reasons=[str(item) for item in payload.get("reasons", [])],
            judgments=[Judgment.from_dict(item) for item in payload.get("judgments", [])],
            computed=dict(payload.get("computed") or {}),
            expected=dict(payload.get("expected") or {}),
            redacted_text=payload.get("redacted_text"),
            latency_ms=_optional_float(payload.get("latency_ms")),
            request_id=payload.get("request_id"),
            error_code=payload.get("error_code"),
            mock=bool(payload.get("mock", False)),
            backend=cast(Literal["jev", "code", "mock"], payload.get("backend") or ("mock" if payload.get("mock") else "jev")),
        )
