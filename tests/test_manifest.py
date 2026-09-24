"""El manifest congelado se encadena con su evidence, no con el código vivo.

Cadena congelada: datasets en disco == manifest == evidence v7 (sha256s).
El historial v5/v6 queda archivado y su cadena se sigue verificando intacta.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from catalog_judge.config import DEFAULT_MODEL


def _file_sha256(path: Path) -> str:
    from catalog_judge.evaluation import file_sha256

    return file_sha256(path)


def _load_metadata(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))["metadata"]


def test_manifest_chains_to_frozen_v7_evidence(repo_root: Path) -> None:
    from catalog_judge.evaluation import dataset_hash

    evaluations = repo_root / "evaluations"
    manifest_path = evaluations / "holdout_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["model"] == DEFAULT_MODEL
    assert manifest["protocol"] == "v7"
    assert manifest["no_tuning_on_confirmation"] is True
    assert manifest["no_tuning_on_holdout"] is True
    assert manifest["jev_domains"] == ["tickets"]
    assert manifest["code_domains"] == ["retail"]
    for domain, expected in manifest["datasets"].items():
        path = repo_root / expected["path"]
        assert expected["sha256"] == dataset_hash(path)
        assert expected["confirmation_split"] == ("confirmation" if domain == "tickets" else "holdout")
        if domain == "tickets":
            assert expected["confirmation"] == 50
        else:
            assert expected["holdout"] == 20

    manifest_sha = _file_sha256(manifest_path)
    tickets = _load_metadata(evaluations / "tickets_live_50.json")
    assert tickets["holdout_manifest_sha256"] == manifest_sha
    assert tickets["prompt_sha256"] == manifest["prompt_sha256"]["tickets"]
    assert tickets["threshold_sha256"] == manifest["threshold_sha256"]
    assert tickets["dataset_sha256"] == manifest["datasets"]["tickets"]["sha256"]
    assert tickets["dataset"] == "tickets_v7_50.csv"
    assert tickets["mock"] is False
    assert tickets["n"] == 50
    assert tickets["model"] == DEFAULT_MODEL

    retail = _load_metadata(evaluations / "retail_live_20.json")
    assert retail["holdout_manifest_sha256"] == manifest_sha
    assert retail["prompt_sha256"] == manifest["prompt_sha256"]["retail"]
    assert retail["threshold_sha256"] == manifest["threshold_sha256"]
    assert retail["dataset_sha256"] == manifest["datasets"]["retail"]["sha256"]
    assert retail["mock"] is False
    assert retail["n"] == 20


def test_v6_archive_chain_stays_intact(repo_root: Path) -> None:
    from catalog_judge.evaluation import dataset_hash

    archive = repo_root / "evaluations" / "archive" / "protocol_v6"
    manifest_path = archive / "holdout_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["protocol"] == "v6"

    manifest_sha = _file_sha256(manifest_path)
    tickets = _load_metadata(archive / "tickets_live_50.json")
    assert tickets["holdout_manifest_sha256"] == manifest_sha
    assert tickets["prompt_sha256"] == manifest["prompt_sha256"]["tickets"]
    assert tickets["threshold_sha256"] == manifest["threshold_sha256"]
    assert tickets["dataset_sha256"] == manifest["datasets"]["tickets"]["sha256"]
    assert tickets["dataset"] == "tickets_v6_50.csv"
    assert manifest["datasets"]["tickets"]["sha256"] == dataset_hash(repo_root / "tickets" / "data" / "tickets_v6_50.csv")

    retail = _load_metadata(archive / "retail_live_20.json")
    assert retail["holdout_manifest_sha256"] == manifest_sha
    assert retail["dataset_sha256"] == manifest["datasets"]["retail"]["sha256"]
    assert retail["prompt_sha256"] == manifest["prompt_sha256"]["retail"]


def test_v5_archive_chain_stays_intact(repo_root: Path) -> None:
    from catalog_judge.evaluation import dataset_hash

    archive = repo_root / "evaluations" / "archive" / "protocol_v5"
    manifest_path = archive / "holdout_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["protocol"] == "v5"

    manifest_sha = _file_sha256(manifest_path)
    tickets = _load_metadata(archive / "tickets_live_50.json")
    assert tickets["holdout_manifest_sha256"] == manifest_sha
    assert tickets["prompt_sha256"] == manifest["prompt_sha256"]["tickets"]
    assert tickets["threshold_sha256"] == manifest["threshold_sha256"]
    assert tickets["dataset_sha256"] == manifest["datasets"]["tickets"]["sha256"]
    assert tickets["dataset"] == "tickets_v5_50.csv"
    # El lote v5 sigue en el repo: su hash en disco coincide con el archivado.
    assert manifest["datasets"]["tickets"]["sha256"] == dataset_hash(repo_root / "tickets" / "data" / "tickets_v5_50.csv")

    retail = _load_metadata(archive / "retail_live_20.json")
    # Asimetría conocida de v5: retail se corrió antes del re-freeze final;
    # encadena dataset y prompt, pero no manifest ni thresholds.
    assert retail["dataset_sha256"] == manifest["datasets"]["retail"]["sha256"]
    assert retail["prompt_sha256"] == manifest["prompt_sha256"]["retail"]


def test_freeze_refuses_to_overwrite_manifest(repo_root: Path) -> None:
    """Congelar con un manifest ya en disco debe fallar sin pisarlo."""
    before = _file_sha256(repo_root / "evaluations" / "holdout_manifest.json")
    completed = subprocess.run(
        [sys.executable, "scripts/freeze_evaluation.py"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "ya existe un manifest congelado" in (completed.stdout + completed.stderr)
    assert _file_sha256(repo_root / "evaluations" / "holdout_manifest.json") == before
