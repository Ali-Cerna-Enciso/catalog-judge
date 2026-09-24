"""Features y política determinista para el fixture público de Favorita.

El mirror público no contiene stock, costo ni margen. Por eso el código
calcula proxies de demanda y nunca presenta `demand_drop_alert` como quiebre
de inventario.
"""

from __future__ import annotations

from typing import Any

from .contracts import Judgment, Route
from .privacy import redact_state, safe_preview

DECISION_TO_ROUTE: dict[str, Route] = {
    "include": "accept",
    "review": "review",
    "exclude": "block",
}

RETAIL_POLICY: dict[str, Any] = {
    "policy_version": "favorita-demand-policy-v4",
    "source_note": "Favorita public demand data; no stock, cost, margin, or inventory fields.",
    "judge": "code",
    "thresholds": {
        "demand_drop_ratio": 0.75,
        "replenishment_candidate_ratio": 1.10,
        "candidate_active_day_share": 0.35,
        "handling_risk_sales_cv": 1.00,
        "handling_risk_active_day_share": 0.25,
        "handling_risk_promo_share": 0.50,
        "exception_sales_cv": 1.50,
        "exception_active_day_share": 0.15,
        "exclude_active_day_share": 0.10,
    },
    "definitions": {
        "avg_sales": "media de sales en las filas públicas de la serie",
        "sales_cv": "desviación poblacional / abs(media), en código",
        "active_day_share": "proporción de registros con sales > 0",
        "promo_share": "proporción de registros con onpromotion > 0",
        "recent_vs_previous_ratio": "media de los últimos 28 días / media de los 28 días previos",
        "demand_drop_alert": "proxy de caída: ratio < 0.75 y avg_sales > 0",
        "replenishment_candidate": "proxy de aumento: ratio >= 1.10 y active_day_share >= 0.35",
    },
}


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "si", "sí"}


def demand_band(value: float, cuts: tuple[float, ...], labels: tuple[str, ...]) -> str:
    """Bucketiza un float en una banda nombrada; los cortes viven en código."""
    assert len(cuts) + 1 == len(labels), "cada corte separa dos bandas"
    for cut, label in zip(cuts, labels, strict=False):
        if value < cut:
            return label
    return labels[-1]


def demand_bands(avg_sales: float, sales_cv: float, active_share: float, promo_share: float, ratio: float | None) -> dict[str, str]:
    """Bandas nombradas: los bordes de política del gold caen en bordes de banda.

    `trend` usa los cortes de la política (0.75 caída, 1.10 repunte);
    `volatility=extrema` arranca en cv 1.00, `presence=muy_baja` bajo
    0.25 y `promo=alta` desde 0.50; el resto por cuantiles del fixture.
    Jev lee nombres, no floats: la aritmética queda en código.
    """
    if ratio is None or avg_sales <= 0:
        trend = "insuficiente"
    elif ratio < 0.75:
        trend = "caida"
    elif ratio >= 1.10:
        trend = "creciente"
    else:
        trend = "estable"
    return {
        "volume": demand_band(avg_sales, (5.0, 250.0, 700.0), ("muy_baja", "baja", "media", "alta")),
        "trend": trend,
        "presence": demand_band(active_share, (0.25, 0.60, 0.94), ("muy_baja", "baja", "media", "alta")),
        "volatility": demand_band(sales_cv, (0.45, 0.75, 1.00), ("baja", "moderada", "alta", "extrema")),
        "promo": demand_band(promo_share, (0.06, 0.39, 0.50), ("nula", "ligera", "media", "alta")),
    }


def demand_pattern(ratio: float | None, avg_sales: float) -> str:
    if ratio is None or avg_sales <= 0:
        return "insufficient"
    if ratio < float(RETAIL_POLICY["thresholds"]["demand_drop_ratio"]):
        return "declining"
    if ratio >= float(RETAIL_POLICY["thresholds"]["replenishment_candidate_ratio"]):
        return "growing"
    return "stable"


def calculate_retail_metrics(row: dict[str, Any]) -> dict[str, Any]:
    """Calcula features y proxies; no devuelve gold ni stock/costo/margen."""
    thresholds = RETAIL_POLICY["thresholds"]
    avg_sales = float(row["avg_sales"])
    sales_cv = float(row["sales_cv"])
    active_share = float(row["active_day_share"])
    promo_share = float(row["promo_share"])
    raw_ratio = row.get("recent_vs_previous_ratio")
    ratio = None if raw_ratio in (None, "") else float(str(raw_ratio))
    pattern = demand_pattern(ratio, avg_sales)
    drop = bool(
        avg_sales > 0
        and ratio is not None
        and ratio < float(thresholds["demand_drop_ratio"])
    )
    candidate = bool(
        avg_sales > 0
        and ratio is not None
        and ratio >= float(thresholds["replenishment_candidate_ratio"])
        and active_share >= float(thresholds["candidate_active_day_share"])
    )
    return {
        "avg_sales": avg_sales,
        "sales_cv": sales_cv,
        "active_day_share": active_share,
        "promo_share": promo_share,
        "recent_vs_previous_ratio": ratio,
        "demand_pattern": pattern,
        "demand_bands": demand_bands(avg_sales, sales_cv, active_share, promo_share, ratio),
        "demand_drop_alert": drop,
        "replenishment_candidate": candidate,
    }


def build_retail_state(row: dict[str, Any]) -> dict[str, Any]:
    """Arma un state público; no incluye expected_* ni una respuesta de policy."""
    metrics = calculate_retail_metrics(row)
    state = {
        "domain": "retail",
        "series_id": str(row["series_id"]),
        "store_nbr": int(row["store_nbr"]),
        "family": str(row["family"]),
        "feature_window": {
            "start": str(row.get("feature_window_start", "")),
            "end": str(row.get("feature_window_end", "")),
        },
        "demand_features": {
            "avg_sales": metrics["avg_sales"],
            "sales_cv": metrics["sales_cv"],
            "active_day_share": metrics["active_day_share"],
            "promo_share": metrics["promo_share"],
            "recent_vs_previous_ratio": metrics["recent_vs_previous_ratio"],
        },
        "demand_bands": metrics["demand_bands"],
        "demand_pattern": metrics["demand_pattern"],
        "demand_drop_alert": metrics["demand_drop_alert"],
        "replenishment_candidate": metrics["replenishment_candidate"],
    }
    return redact_state(state)


def classify_retail_policy(row: dict[str, Any]) -> dict[str, Any]:
    """Aplica la política de demanda en código, sin llamadas a Jev.

    El gold del fixture se genera con esta misma función: la accuracy
    contra `expected_*` es una prueba de regresión de la política.
    """
    metrics = calculate_retail_metrics(row)
    thresholds = RETAIL_POLICY["thresholds"]
    avg = float(metrics["avg_sales"])
    cv = float(metrics["sales_cv"])
    active = float(metrics["active_day_share"])
    promo = float(metrics["promo_share"])
    drop = bool(metrics["demand_drop_alert"])
    candidate = bool(metrics["replenishment_candidate"])
    risk = bool(
        cv >= float(thresholds["handling_risk_sales_cv"])
        or active < float(thresholds["handling_risk_active_day_share"])
        or promo >= float(thresholds["handling_risk_promo_share"])
    )
    exception = bool(
        drop
        or cv >= float(thresholds["exception_sales_cv"])
        or active < float(thresholds["exception_active_day_share"])
    )
    if avg <= 0 or active < float(thresholds["exclude_active_day_share"]):
        decision = "exclude"
    elif drop or risk or exception:
        decision = "review"
    else:
        decision = "include"
    route = DECISION_TO_ROUTE[decision]
    reasons: list[str] = []
    if decision == "exclude":
        reasons.append("series_decision=exclude")
    elif decision == "review":
        reasons.append("series_decision=review")
    if drop:
        reasons.append("demand_drop_alert_proxy_codigo")
    if risk:
        reasons.append("handling_risk_codigo")
    if exception:
        reasons.append("exception_needed_codigo")
    if metrics["demand_pattern"] == "insufficient":
        reasons.append("demanda_insuficiente_codigo")
    return {
        **metrics,
        "series_decision": decision,
        "handling_risk": risk,
        "exception_needed": exception,
        "route": route,
        "reasons": reasons or ["aceptacion_por_politica"],
        "policy_version": RETAIL_POLICY["policy_version"],
        "judge": "code",
        "replenishment_candidate": candidate,
    }


def retail_policy_judgments(policy: dict[str, Any]) -> list[Judgment]:
    """Materializa el contrato de 3 juicios desde la política de código."""
    decision = str(policy["series_decision"])
    risk = 1.0 if policy["handling_risk"] else 0.0
    exception = 1.0 if policy["exception_needed"] else 0.0
    return [
        Judgment("series_decision", "choice", decision, confidence=1.0, choice=decision),
        Judgment("handling_risk", "noul", risk, noul=risk),
        Judgment("exception_needed", "noul", exception, noul=exception),
    ]


def expected_fields(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: row[key]
        for key in (
            "expected_series_decision",
            "expected_handling_risk",
            "expected_exception_needed",
            "expected_route",
        )
        if key in row
    }


def retail_row_id(row: dict[str, Any]) -> str:
    return str(row["series_id"])


def retail_preview(row: dict[str, Any]) -> str:
    return safe_preview(f"series_id {row.get('series_id', '')} · family {row.get('family', '')}", 180)


def policy_payload() -> dict[str, Any]:
    """Copia serializable de la política para `retail/policy.json`."""
    return {
        "version": RETAIL_POLICY["policy_version"],
        "source_note": RETAIL_POLICY["source_note"],
        "judge": RETAIL_POLICY["judge"],
        "thresholds": RETAIL_POLICY["thresholds"],
        "definitions": RETAIL_POLICY["definitions"],
        "outputs": ["series_decision", "handling_risk", "exception_needed", "route"],
    }
