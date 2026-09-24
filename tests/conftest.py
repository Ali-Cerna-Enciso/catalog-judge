"""Fixtures locales; ningún test necesita red ni credenciales."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def repo_root() -> Path:
    return ROOT


@pytest.fixture
def retail_sample(repo_root: Path) -> Path:
    return repo_root / "retail" / "data" / "favorita_demand_96.csv"


@pytest.fixture
def tickets_sample(repo_root: Path) -> Path:
    return repo_root / "tickets" / "data" / "tickets_100.csv"
