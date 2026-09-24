from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import httpx2
import pytest
import typesafe_sdk

from catalog_judge.config import Settings
from catalog_judge.jev_client import BackendError, JevBackend
from catalog_judge.prompts import retail_questions


def test_importing_package_and_prompts_does_not_import_sdk() -> None:
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src") + os.pathsep + env.get("PYTHONPATH", "")
    code = "import sys; import catalog_judge; assert 'typesafe_sdk' not in sys.modules; import catalog_judge.prompts; assert 'typesafe_sdk' not in sys.modules; print('lazy-ok')"
    completed = subprocess.run([sys.executable, "-c", code], cwd=root, env=env, capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr
    assert "lazy-ok" in completed.stdout


def test_live_requires_consent_key_and_pinned_model() -> None:
    with pytest.raises(BackendError) as consent:
        JevBackend(Settings(api_key="unit-test-key"), allow_remote=False)
    assert consent.value.code == "remote_consent_required"
    with pytest.raises(BackendError) as missing:
        JevBackend(Settings(api_key=None), allow_remote=True)
    assert missing.value.code == "missing_api_key"
    with pytest.raises(BackendError) as model:
        JevBackend(Settings(api_key="unit-test-key", model="jev-latest"), allow_remote=True)
    assert model.value.code == "model_not_pinned"


def test_real_wrapper_sanitizes_and_restores_log_level(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured["init"] = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def system_one(self, state, questions, *, model):
            captured["state"] = state
            captured["model"] = model
            return {"answers": {}, "model": model}

    monkeypatch.setenv("TYPESAFE_LOG_LEVEL", "sentinel")
    monkeypatch.setattr(typesafe_sdk, "TypeSafeClient", FakeClient)
    backend = JevBackend(Settings(api_key="unit-test-key", model="jev-1.13.0"), allow_remote=True)
    backend.classify({"texto": "Escriban a demo@example.invalid"}, retail_questions())
    assert os.environ["TYPESAFE_LOG_LEVEL"] == "sentinel"
    assert "demo@example.invalid" not in str(captured["state"])
    assert "EMAIL_PLACEHOLDER" in str(captured["state"])


def test_real_wrapper_maps_http_error_without_body(monkeypatch) -> None:
    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def system_one(self, state, questions, *, model):
            raise typesafe_sdk.TypeSafeAPIError(429, {"secret": "never-log"}, httpx2.Headers())

    monkeypatch.setattr(typesafe_sdk, "TypeSafeClient", FakeClient)
    backend = JevBackend(Settings(api_key="unit-test-key"), allow_remote=True)
    with pytest.raises(BackendError) as raised:
        backend.classify({"texto": "sintético"}, retail_questions())
    assert raised.value.code == "rate_limited"
    assert "never-log" not in str(raised.value)


def test_live_rejects_debug_logging() -> None:
    with pytest.raises(BackendError) as raised:
        JevBackend(Settings(api_key="unit-test-key", log_level="debug"), allow_remote=True)
    assert raised.value.code == "unsafe_log_level"
