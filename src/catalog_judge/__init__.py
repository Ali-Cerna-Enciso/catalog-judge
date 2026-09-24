"""Catálogo Judge: clasificación masiva con Jev y agregación determinista.

Los prompts y el SDK se importan de forma perezosa: importar el paquete no
arranca el SDK ni necesita una API key.
"""

from __future__ import annotations

import importlib
from typing import Any

from .config import DEFAULT_MODEL, Settings
from .contracts import Judgment, RowResult

__all__ = [
    "DEFAULT_MODEL",
    "Settings",
    "Judgment",
    "RowResult",
    "RETAIL_QUESTION_IDS",
    "TICKET_QUESTION_IDS",
    "retail_questions",
    "tickets_questions",
]

_LAZY_EXPORTS = {
    "RETAIL_QUESTION_IDS",
    "TICKET_QUESTION_IDS",
    "retail_questions",
    "tickets_questions",
}


def __getattr__(name: str) -> Any:
    """Carga prompts sólo cuando se solicita uno de esos exports."""
    if name in _LAZY_EXPORTS:
        module = importlib.import_module(".prompts", __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__version__ = "0.1.0"
