from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_app_opens_versioned_samples_without_upload() -> None:
    root = Path(__file__).resolve().parents[1]
    app = AppTest.from_file(root / "app.py", default_timeout=20)
    app.run()
    assert not app.exception
    assert {tab.label for tab in app.tabs} == {"Retail", "Tickets", "Evidence / Report"}
