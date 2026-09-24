"""Configuración local del harness.

La API key se mantiene fuera de logs, de las representaciones y de los exports.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_MODEL = "jev-1.13.0"
DEFAULT_BASE_URL = "https://api.typesafe.ai"


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "si", "sí", "on"}


@dataclass(frozen=True)
class Settings:
    """Configuración de ejecución; ``api_key`` nunca se imprime."""

    api_key: str | None = field(default=None, repr=False)
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    timeout_seconds: float = 20.0
    allow_remote: bool = False
    log_level: str = "warning"

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    @classmethod
    def from_env(cls, dotenv_path: str | Path | None = None) -> Settings:
        """Lee configuración sin convertir secretos en logs.

        ``load_dotenv`` no sobrescribe variables ya presentes. Si se entrega un
        ``dotenv_path`` explícito, se carga sólo ese archivo.
        """

        if dotenv_path is not None:
            load_dotenv(dotenv_path, override=False)
        else:
            load_dotenv(override=False)

        key = os.getenv("TYPESAFE_API_KEY")
        key = key.strip() if key else None
        try:
            timeout = float(os.getenv("CATALOG_JUDGE_TIMEOUT", "20"))
        except ValueError:
            timeout = 20.0
        if timeout <= 0:
            timeout = 20.0

        return cls(
            api_key=key,
            base_url=os.getenv("TYPESAFE_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
            model=os.getenv("TYPESAFE_DEFAULT_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL,
            timeout_seconds=timeout,
            allow_remote=_as_bool(os.getenv("CATALOG_JUDGE_ALLOW_REMOTE"), False),
            log_level=os.getenv("TYPESAFE_LOG_LEVEL", "warning").strip().lower() or "warning",
        )

    def public_summary(self) -> dict[str, object]:
        """Resumen seguro para ``doctor`` y auditorías locales."""

        return {
            "model": self.model,
            "base_url": self.base_url,
            "timeout_seconds": self.timeout_seconds,
            "api_key_present": self.has_api_key,
            "remote_consent_env": self.allow_remote,
            "log_level": self.log_level,
        }
