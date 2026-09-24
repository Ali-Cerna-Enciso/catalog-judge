"""Lectura/escritura y validación de CSV para fixtures y exports."""

from __future__ import annotations

import json
import math
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd

from .contracts import RowResult

RETAIL_REQUIRED_COLUMNS = (
    "series_id",
    "store_nbr",
    "family",
    "avg_sales",
    "sales_cv",
    "active_day_share",
    "promo_share",
    "recent_vs_previous_ratio",
    "demand_drop_alert",
    "replenishment_candidate",
)
RETAIL_EXPECTED_COLUMNS = (
    "expected_series_decision",
    "expected_handling_risk",
    "expected_exception_needed",
    "expected_route",
)
TICKET_REQUIRED_COLUMNS = ("source_id", "source_dataset", "subject_es", "body_es", "texto")
# Opcionales: se leen si están; sin ellas esas señales de gold valen 0.0.
TICKET_EXPECTED_COLUMNS = (
    "expected_area",
    "expected_intent",
    "expected_urgency",
    "expected_human",
    "expected_ambiguous",
    "expected_contradictory",
    "expected_security_legal",
    "expected_refund",
    "expected_actionability",
    "expected_technical_repro",
    "expected_route",
)


class CsvSchemaError(ValueError):
    """Error de esquema con campo y fila, sin volcar el contenido de la fila."""


def _clean_cell(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value.strip() if isinstance(value, str) else value


def _number(value: Any, field: str, row_number: int, *, integer: bool = False, optional: bool = False) -> float | int | None:
    value = _clean_cell(value)
    if value in (None, ""):
        if optional:
            return None
        raise CsvSchemaError(f"fila {row_number}: falta {field}")
    try:
        number = float(str(value).replace(",", "."))
    except (TypeError, ValueError) as exc:
        raise CsvSchemaError(f"fila {row_number}: {field} no es numérico") from exc
    if not math.isfinite(number) or number < 0:
        raise CsvSchemaError(f"fila {row_number}: {field} no es un número válido")
    if integer and not number.is_integer():
        raise CsvSchemaError(f"fila {row_number}: {field} debe ser entero")
    return int(number) if integer else number


def _bool(value: Any, field: str, row_number: int, *, optional: bool = False) -> bool | None:
    value = _clean_cell(value)
    if value in (None, ""):
        if optional:
            return None
        raise CsvSchemaError(f"fila {row_number}: falta {field}")
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "t", "yes", "y", "si", "sí"}:
        return True
    if normalized in {"0", "false", "f", "no", "n"}:
        return False
    raise CsvSchemaError(f"fila {row_number}: {field} no es booleano")


def _require_columns(columns: Iterable[str], required: Iterable[str], domain: str) -> None:
    actual = set(columns)
    missing = [column for column in required if column not in actual]
    if missing:
        raise CsvSchemaError(f"{domain}: faltan columnas obligatorias: {', '.join(missing)}")


def _unique_id(row: dict[str, Any], field: str, row_number: int, seen: set[str]) -> str:
    value = str(_clean_cell(row.get(field)) or "").strip()
    if not value:
        raise CsvSchemaError(f"fila {row_number}: falta {field}")
    if value in seen:
        raise CsvSchemaError(f"fila {row_number}: {field} duplicado")
    seen.add(value)
    return value


def _optional_text(row: dict[str, Any], field: str) -> str | None:
    value = _clean_cell(row.get(field))
    return str(value) if value not in (None, "") else None


def normalize_retail_dataframe(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Valida el fixture de demanda; ``series_id`` siempre permanece texto."""
    _require_columns(frame.columns, RETAIL_REQUIRED_COLUMNS, "retail")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, (_, raw) in enumerate(frame.iterrows(), start=2):
        source = raw.to_dict()
        row: dict[str, Any] = {"series_id": _unique_id(source, "series_id", index, seen)}
        row["store_nbr"] = _number(source.get("store_nbr"), "store_nbr", index, integer=True)
        family = _clean_cell(source.get("family"))
        if not family:
            raise CsvSchemaError(f"fila {index}: falta family")
        row["family"] = str(family)
        for field in ("avg_sales", "sales_cv", "active_day_share", "promo_share"):
            row[field] = _number(source.get(field), field, index)
        row["recent_vs_previous_ratio"] = _number(source.get("recent_vs_previous_ratio"), "recent_vs_previous_ratio", index, optional=True)
        row["demand_drop_alert"] = _bool(source.get("demand_drop_alert"), "demand_drop_alert", index)
        row["replenishment_candidate"] = _bool(source.get("replenishment_candidate"), "replenishment_candidate", index)
        for field in ("source_dataset", "feature_version", "feature_window_start", "feature_window_end", "evaluation_split"):
            if field in frame.columns:
                row[field] = _optional_text(source, field)
        if "rows_used" in frame.columns:
            row["rows_used"] = _number(source.get("rows_used"), "rows_used", index, integer=True, optional=True)
        for field in RETAIL_EXPECTED_COLUMNS:
            if field in frame.columns:
                value = _clean_cell(source.get(field))
                if field in {"expected_handling_risk", "expected_exception_needed"}:
                    row[field] = _bool(value, field, index, optional=True)
                else:
                    row[field] = str(value) if value not in (None, "") else None
        rows.append(row)
    return rows


def normalize_tickets_dataframe(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Valida el corpus público curado; nunca exige la columna `answer`."""
    _require_columns(frame.columns, TICKET_REQUIRED_COLUMNS, "tickets")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, (_, raw) in enumerate(frame.iterrows(), start=2):
        source = raw.to_dict()
        row: dict[str, Any] = {"source_id": _unique_id(source, "source_id", index, seen)}
        for field in ("source_dataset", "subject_es", "body_es", "texto", "curation_note", "source_queue", "source_type", "source_priority", "evaluation_split"):
            value = _optional_text(source, field)
            if field in {"source_dataset", "subject_es", "body_es", "texto"} and not value:
                raise CsvSchemaError(f"fila {index}: falta {field}")
            if value is not None:
                row[field] = value
        for field in TICKET_EXPECTED_COLUMNS:
            if field in frame.columns:
                value = _clean_cell(source.get(field))
                if field in {
                    "expected_human",
                    "expected_ambiguous",
                    "expected_contradictory",
                    "expected_security_legal",
                    "expected_refund",
                    "expected_technical_repro",
                }:
                    row[field] = _bool(value, field, index, optional=True)
                else:
                    row[field] = str(value) if value not in (None, "") else None
        rows.append(row)
    return rows


def read_csv(path: str | Path, domain: str, limit: int | None = None) -> list[dict[str, Any]]:
    if domain not in {"retail", "tickets"}:
        raise ValueError("domain debe ser retail o tickets")
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"no existe el CSV: {path}")
    try:
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    except Exception as exc:  # pragma: no cover - pandas message can vary
        raise CsvSchemaError(f"no se pudo leer el CSV: {path.name}") from exc
    rows = normalize_retail_dataframe(frame) if domain == "retail" else normalize_tickets_dataframe(frame)
    if limit is not None:
        if limit < 0:
            raise ValueError("limit no puede ser negativo")
        rows = rows[:limit]
    return rows


def results_to_dataframe(results: Iterable[RowResult], *, include_text: bool = False) -> pd.DataFrame:
    """Aplana resultados; por defecto no incluye texto ni preview."""
    records: list[dict[str, Any]] = []
    for result in results:
        record = result.to_dict(include_judgments=True, include_text=include_text)
        record["judgments"] = json.dumps(record.get("judgments", []), ensure_ascii=False, sort_keys=True)
        record["computed"] = json.dumps(record.get("computed", {}), ensure_ascii=False, sort_keys=True)
        record["expected"] = json.dumps(record.get("expected", {}), ensure_ascii=False, sort_keys=True)
        record["reasons"] = ";".join(result.reasons)
        records.append(record)
    return pd.DataFrame.from_records(records)


def write_results(results: Iterable[RowResult], output: str | Path, *, include_text: bool = False) -> Path:
    """Exporta CSV/JSON; el default es seguro y no incluye texto de entrada."""
    results_list = list(results)
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".json":
        path.write_text(
            json.dumps([item.to_dict(include_judgments=True, include_text=include_text) for item in results_list], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    else:
        results_to_dataframe(results_list, include_text=include_text).to_csv(path, index=False, encoding="utf-8")
    return path


def read_results(path: str | Path) -> list[RowResult]:
    source = Path(path)
    if source.suffix.lower() == ".json":
        payload = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = [payload]
        if not isinstance(payload, list):
            raise CsvSchemaError("el JSON de resultados debe ser una lista")
        return [RowResult.from_dict(item) for item in payload]
    frame = pd.read_csv(source, keep_default_na=False)
    results: list[RowResult] = []
    for _, raw in frame.iterrows():
        record = raw.to_dict()
        for field in ("judgments", "computed", "expected"):
            value = record.get(field)
            if isinstance(value, str) and value:
                try:
                    record[field] = json.loads(value)
                except json.JSONDecodeError:
                    record[field] = {}
        record.setdefault("reasons", [])
        if isinstance(record.get("reasons"), str):
            record["reasons"] = [x for x in record["reasons"].split(";") if x]
        if isinstance(record.get("mock"), str):
            record["mock"] = record["mock"].strip().lower() in {"1", "true", "yes", "si", "sí"}
        results.append(RowResult.from_dict(record))
    return results
