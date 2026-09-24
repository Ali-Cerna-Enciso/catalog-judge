"""Agregaciones de ejecución: conteos, rutas, errores y latencias por corrida."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Any

from .contracts import RowResult
from .prompts import RETAIL_QUESTION_IDS, TICKET_QUESTION_IDS


def summarize_results(results: Iterable[RowResult]) -> dict[str, Any]:
    items = list(results)
    routes = Counter(item.route for item in items)
    statuses = Counter(item.status for item in items)
    errors = Counter(item.error_code for item in items if item.error_code)

    def expected_count(item: RowResult) -> int:
        return len(RETAIL_QUESTION_IDS) if item.domain == "retail" else len(TICKET_QUESTION_IDS)

    expected_judgments = sum(expected_count(item) for item in items)
    valid_judgments = sum(len(item.judgments) for item in items)
    valid_responses = sum(item.status == "ok" and len(item.judgments) == expected_count(item) for item in items)
    completed_requests = sum(item.status == "ok" for item in items)
    latencies = [float(item.latency_ms) for item in items if item.latency_ms is not None]
    summary: dict[str, Any] = {
        "rows": len(items),
        "requests_completed": completed_requests,
        "valid_responses": valid_responses,
        "valid_judgments": valid_judgments,
        "expected_judgments": expected_judgments,
        "contract_coverage": round(valid_responses / len(items), 6) if items else 0.0,
        "routes": dict(routes),
        "statuses": dict(statuses),
        "errors": dict(errors),
        "mock": all(item.mock for item in items) if items else True,
        "backend": items[0].backend if items else None,
        "latency_ms_mean": round(sum(latencies) / len(latencies), 3) if latencies else None,
        "latency_ms_max": round(max(latencies), 3) if latencies else None,
    }
    if items and items[0].domain == "retail":
        summary["demand_drop_alerts"] = sum(bool(item.computed.get("demand_drop_alert")) for item in items)
        summary["replenishment_candidates"] = sum(bool(item.computed.get("replenishment_candidate")) for item in items)
    else:
        areas: Counter[str] = Counter()
        destinations: Counter[str] = Counter()
        for item in items:
            area = item.judgment_map().get("area")
            if area is not None and area.choice:
                areas[area.choice] += 1
            if item.computed.get("destination"):
                destinations[item.computed["destination"]] += 1
        summary["areas"] = dict(areas)
        summary["destinations"] = dict(destinations)
    return summary
