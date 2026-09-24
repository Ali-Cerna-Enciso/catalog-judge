"""Sanitización local básica antes de cualquier llamada live.

Es una barrera básica de PII: patrones comunes y un flag local para que
la fila vaya a revisión (detalles y límites en SECURITY.md).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b", re.IGNORECASE)
CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
DNI_RE = re.compile(r"(?<!\d)\d{8}(?!\d)")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?51[\s.-]?)?9(?:[\s.-]?\d){8}(?!\d)")


def redact_text(value: str) -> str:
    """Sustituye email, teléfono, DNI y tarjetas por placeholders estables."""

    sanitized = EMAIL_RE.sub("<EMAIL_PLACEHOLDER>", value)
    sanitized = CARD_RE.sub("<CARD_PLACEHOLDER>", sanitized)
    sanitized = DNI_RE.sub("<DNI_PLACEHOLDER>", sanitized)
    sanitized = PHONE_RE.sub("<PHONE_PLACEHOLDER>", sanitized)
    return sanitized


def contains_pii(value: str) -> bool:
    """Indica si se detectó un patrón básico, sin devolver el valor detectado."""

    return bool(EMAIL_RE.search(value) or CARD_RE.search(value) or DNI_RE.search(value) or PHONE_RE.search(value))


def redact_state(value: Any) -> Any:
    """Sustituye recursivamente strings por valores sanitizados."""

    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {str(key): redact_state(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_state(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_state(item) for item in value)
    return value


def safe_preview(value: str, max_chars: int = 240) -> str:
    """Preview corto y sanitizado para detalle/UI, nunca para un log de request."""

    clean = redact_text(value).replace("\n", " ").strip()
    if len(clean) <= max_chars:
        return clean
    return clean[: max_chars - 1].rstrip() + "…"
