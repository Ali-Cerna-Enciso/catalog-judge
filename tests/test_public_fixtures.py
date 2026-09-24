from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import pytest

from catalog_judge.csv_io import CsvSchemaError, read_csv


def test_retail_fixture_is_public_demand_proxy(retail_sample: Path) -> None:
    frame = pd.read_csv(retail_sample)
    assert len(frame) == 96
    assert frame["series_id"].nunique() == 96
    assert frame["family"].nunique() >= 8
    assert set(frame["evaluation_split"]) == {"dev", "holdout"}
    assert (frame["evaluation_split"] == "holdout").sum() == 20
    assert not {"stock", "stock_disponible", "costo", "cost", "margen", "margin"}.intersection(frame.columns)
    assert frame["source_dataset"].eq("t4tiana/store-sales-time-series-forecasting").all()
    assert set(frame["demand_drop_alert"].astype(str).str.lower()) <= {"true", "false"}
    assert set(frame["replenishment_candidate"].astype(str).str.lower()) <= {"true", "false"}
    assert frame["expected_series_decision"].isin({"include", "review", "exclude"}).all()


def test_tickets_fixture_is_substantively_distinct_and_curated(tickets_sample: Path, repo_root: Path) -> None:
    frame = pd.read_csv(tickets_sample)
    assert len(frame) == 100
    assert frame["source_id"].nunique() == 100
    assert frame["texto"].nunique() == 100
    assert frame["texto"].str[:80].nunique() == 100
    assert "answer" not in frame.columns
    assert set(frame["evaluation_split"]) == {"dev", "holdout"}
    assert (frame["evaluation_split"] == "holdout").sum() == 50
    assert frame["expected_area"].nunique() >= 8
    assert set(frame["expected_urgency"]) == {"low", "medium", "high", "critical"}
    assert set(frame["expected_intent"]) == {"consulta", "incidencia", "reclamo", "solicitud", "retroalimentacion"}
    assert set(frame["expected_actionability"]) == {"no_action", "clarification", "standard_action", "immediate_action"}
    assert set(frame["expected_human"].astype(str).str.lower()) <= {"true", "false"}
    assert set(frame["expected_security_legal"].astype(str).str.lower()) <= {"true", "false"}
    assert set(frame["expected_refund"].astype(str).str.lower()) <= {"true", "false"}
    forbidden = re.compile(r"Hola, equipo|Caso sintético|@|\+51|\b\d{8}\b|https?://", re.I)
    assert not frame["subject_es"].str.contains(forbidden).any()
    assert not frame["body_es"].str.contains(forbidden).any()
    curation = json.loads((repo_root / "tickets" / "data" / "curation_100.json").read_text(encoding="utf-8"))
    assert curation["license"] == "CC BY-NC 4.0"
    assert sum(len(entries) for entries in curation["groups"].values()) == 100


def test_retail_code_policy_matches_fixture_gold(retail_sample: Path) -> None:
    from catalog_judge.retail import classify_retail_policy

    rows = read_csv(retail_sample, "retail")
    for row in rows:
        policy = classify_retail_policy(row)
        assert policy["series_decision"] == row["expected_series_decision"]
        assert policy["handling_risk"] == row["expected_handling_risk"]
        assert policy["exception_needed"] == row["expected_exception_needed"]
        assert policy["route"] == row["expected_route"]
        assert policy["demand_drop_alert"] == row["demand_drop_alert"]
        assert policy["replenishment_candidate"] == row["replenishment_candidate"]


def test_v5_confirmation_fixture_is_new_and_composed(repo_root: Path) -> None:
    from catalog_judge.tickets import compose_expected_route

    path = repo_root / "tickets" / "data" / "tickets_v5_50.csv"
    frame = pd.read_csv(path)
    assert len(frame) == 50
    assert frame["source_id"].nunique() == 50
    assert frame["texto"].nunique() == 50
    assert set(frame["evaluation_split"]) == {"confirmation"}
    assert not frame["source_id"].astype(str).str.startswith("hf-row-").any()
    rows = read_csv(path, "tickets")
    for row in rows:
        assert compose_expected_route(row) == row["expected_route"]


def test_v6_confirmation_fixture_still_composes_without_optional_columns(repo_root: Path) -> None:
    """Lote v6 (sin columnas nuevas): fallback 0.0 y ruta gold intacta."""
    from catalog_judge.tickets import compose_expected_route, gold_as_judgments

    path = repo_root / "tickets" / "data" / "tickets_v6_50.csv"
    rows = read_csv(path, "tickets")
    assert len(rows) == 50
    for row in rows:
        assert "expected_ambiguous" not in row
        assert "expected_contradictory" not in row
        values = {item.question_id: item for item in gold_as_judgments(row)}
        assert values["is_ambiguous"].noul == 0.0
        assert values["is_contradictory"].noul == 0.0
        assert compose_expected_route(row) == row["expected_route"]


def test_v7_confirmation_fixture_has_optional_signals_and_composes(repo_root: Path) -> None:
    """Lote v7: columnas nuevas presentes y ruta gold = compose_expected_route."""
    from catalog_judge.tickets import compose_expected_route, gold_as_judgments

    path = repo_root / "tickets" / "data" / "tickets_v7_50.csv"
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    assert len(frame) == 50
    assert list(frame.columns)[11:14] == [
        "expected_human",
        "expected_ambiguous",
        "expected_contradictory",
    ]
    assert frame["source_id"].tolist() == [f"v7-row-{i:03d}" for i in range(1, 51)]
    assert set(frame["evaluation_split"]) == {"confirmation"}
    rows = read_csv(path, "tickets")
    assert len(rows) == 50
    for row in rows:
        assert "expected_ambiguous" in row
        assert "expected_contradictory" in row
        assert isinstance(row["expected_ambiguous"], bool)
        assert isinstance(row["expected_contradictory"], bool)
        values = {item.question_id: item for item in gold_as_judgments(row)}
        assert values["is_ambiguous"].noul == (1.0 if row["expected_ambiguous"] else 0.0)
        assert values["is_contradictory"].noul == (1.0 if row["expected_contradictory"] else 0.0)
        assert compose_expected_route(row) == row["expected_route"]


def test_csv_loader_rejects_old_schema(tmp_path: Path) -> None:
    old = tmp_path / "old.csv"
    pd.DataFrame([{"sku": "RJ-001", "producto": "old"}]).to_csv(old, index=False)
    with pytest.raises(CsvSchemaError):
        read_csv(old, "retail")
