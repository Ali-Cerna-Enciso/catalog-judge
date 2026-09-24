"""Evaluación live reproducible contra gold, separada del mock."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contracts import RowResult
from .csv_io import read_results
from .prompts import RETAIL_QUESTION_IDS, TICKET_QUESTION_IDS, tickets_questions
from .retail import RETAIL_POLICY
from .routing import DEFAULT_THRESHOLDS, HUMAN_SIGNAL_CUTS, RoutingThresholds, modal_level
from .tickets import TEAM_POLICY, build_ticket_state

ACTIONABILITY_LABELS = ("no_action", "clarification", "standard_action", "immediate_action")
URGENCY_LABELS = ("low", "medium", "high", "critical")
# Corte legacy para evidence archivada sin las tres señales humanas.
LEGACY_REQUIRES_HUMAN_NOUL = 0.50


def _safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _as_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "si", "sí"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    return None


def classification_metrics(y_true: Sequence[str], y_pred: Sequence[str | None], labels: Sequence[str]) -> dict[str, Any]:
    labels = list(dict.fromkeys(labels))
    per_label: dict[str, dict[str, float]] = {}
    confusion: dict[str, dict[str, int]] = {truth: {pred: 0 for pred in labels} for truth in labels}
    for truth, prediction in zip(y_true, y_pred, strict=True):
        if truth in confusion:
            key = prediction if prediction in labels else "__missing__"
            confusion[truth][key] = confusion[truth].get(key, 0) + 1
    for label in labels:
        tp = confusion[label].get(label, 0)
        fp = sum(confusion[truth].get(label, 0) for truth in labels if truth != label)
        fn = sum(confusion[label].get(pred, 0) for pred in confusion[label] if pred != label)
        precision = _safe_div(tp, tp + fp)
        recall = _safe_div(tp, tp + fn)
        f1 = _safe_div(2 * precision * recall, precision + recall)
        per_label[label] = {"precision": precision, "recall": recall, "f1": f1, "support": tp + fn}
    correct = sum(truth == prediction for truth, prediction in zip(y_true, y_pred, strict=True))
    return {
        "accuracy": _safe_div(correct, len(y_true)),
        "macro_precision": _safe_div(sum(item["precision"] for item in per_label.values()), len(per_label)),
        "macro_recall": _safe_div(sum(item["recall"] for item in per_label.values()), len(per_label)),
        "macro_f1": _safe_div(sum(item["f1"] for item in per_label.values()), len(per_label)),
        "per_label": per_label,
        "confusion": confusion,
    }


def _answer(result: RowResult, question_id: str):
    return result.judgment_map().get(question_id)


def _choice(result: RowResult, question_id: str) -> str | None:
    answer = _answer(result, question_id)
    return answer.choice if answer is not None else None


def _score_label(result: RowResult, question_id: str, labels: Sequence[str]) -> str | None:
    answer = _answer(result, question_id)
    if answer is None:
        return None
    level = modal_level(answer, len(labels))
    if level is None:
        return None
    return labels[level]


def _noul_decision(result: RowResult, question_id: str, threshold: float) -> bool | None:
    answer = _answer(result, question_id)
    if answer is None or answer.noul is None:
        return None
    return answer.noul >= threshold


def _human_signal_composition(result: RowResult) -> bool | None:
    """Predicción humana: OR de las tres señales Noul con sus cortes.

    Mismo criterio que `route_tickets` (lista compartida `HUMAN_SIGNAL_CUTS`).
    En evidence archivada legacy sólo existe `requires_human`: ahí cae al
    corte histórico.
    """
    decisions: list[bool] = []
    for question_id, attr in HUMAN_SIGNAL_CUTS:
        answer = _answer(result, question_id)
        if answer is not None and answer.noul is not None:
            decisions.append(answer.noul >= getattr(DEFAULT_THRESHOLDS, attr))
    if decisions:
        return any(decisions)
    return _noul_decision(result, "requires_human", LEGACY_REQUIRES_HUMAN_NOUL)


def _adjacent_accuracy(truth: Sequence[str], predicted: Sequence[str | None], labels: Sequence[str]) -> dict[str, Any]:
    """Exactitud ordinal: acierto si la predicción cae en el gold o un vecino."""
    index = {label: i for i, label in enumerate(labels)}
    comparable = [
        (expected, prediction)
        for expected, prediction in zip(truth, predicted, strict=True)
        if expected in index and prediction in index
    ]
    exact = sum(expected == prediction for expected, prediction in comparable)
    adjacent = sum(abs(index[expected] - index[prediction]) <= 1 for expected, prediction in comparable)
    mae = (
        sum(abs(index[expected] - index[prediction]) for expected, prediction in comparable) / len(comparable)
        if comparable
        else None
    )
    return {
        "accuracy": _safe_div(exact, len(comparable)),
        "adjacent_accuracy": _safe_div(adjacent, len(comparable)),
        "mae": None if mae is None else round(mae, 6),
        "n": len(comparable),
        "missing_predictions": len(truth) - len(comparable),
    }


def _label_recall(truth: Sequence[str], predicted: Sequence[str], label: str) -> dict[str, Any]:
    support = sum(item == label for item in truth)
    hits = sum(expected == label and prediction == label for expected, prediction in zip(truth, predicted, strict=True))
    return {"label": label, "recall": _safe_div(hits, support), "hits": hits, "support": support}


def _binary_accuracy(truth: list[bool | None], predicted: list[bool | None]) -> dict[str, Any]:
    valid = [(expected, prediction) for expected, prediction in zip(truth, predicted, strict=True) if expected is not None]
    correct = sum(prediction == expected for expected, prediction in valid)
    return {"accuracy": _safe_div(correct, len(valid)), "n": len(valid), "missing_predictions": len(truth) - len(valid)}


def _execution_stats(items: list[RowResult]) -> dict[str, Any]:
    latencies = [float(item.latency_ms) for item in items if item.latency_ms is not None]
    errors: dict[str, int] = {}
    for item in items:
        if item.error_code:
            errors[item.error_code] = errors.get(item.error_code, 0) + 1
    valid = sum(
        item.status == "ok"
        and len(item.judgments) == (len(RETAIL_QUESTION_IDS) if item.domain == "retail" else len(TICKET_QUESTION_IDS))
        for item in items
    )
    expected_judgments = sum(
        len(RETAIL_QUESTION_IDS) if item.domain == "retail" else len(TICKET_QUESTION_IDS) for item in items
    )
    valid_judgments = sum(len(item.judgments) for item in items)
    return {
        "n": len(items),
        "requests_completed": sum(item.status == "ok" for item in items),
        "valid_responses": valid,
        "valid_judgments": valid_judgments,
        "expected_judgments": expected_judgments,
        "contract_coverage": round(valid / len(items), 6) if items else 0.0,
        "errors": errors,
        "error_count": sum(errors.values()),
        "latency_ms_mean": round(sum(latencies) / len(latencies), 3) if latencies else None,
        "latency_ms_max": round(max(latencies), 3) if latencies else None,
    }


def evaluate_results(results: Iterable[RowResult], domain: str | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    items = list(results)
    if not items:
        return {"n": 0, "warnings": ["sin filas para evaluar"]}
    domain = domain or items[0].domain
    stats = _execution_stats(items)
    warnings = ["MOCK_EVALUATION_ONLY: el mock heurístico no mide Jev real."] if any(item.mock for item in items) else []
    warnings.append("Las métricas son de un holdout pequeño; no son un benchmark de producción.")
    if metadata:
        stats["metadata"] = metadata
    if domain == "retail":
        decision_truth = [str(item.expected.get("expected_series_decision", "")) for item in items]
        decision_pred = [_choice(item, "series_decision") for item in items]
        decision_labels = [label for label in ["include", "review", "exclude"] if label in decision_truth or label in decision_pred]
        risk_truth = [_as_bool(item.expected.get("expected_handling_risk")) for item in items]
        risk_pred = [_noul_decision(item, "handling_risk", DEFAULT_THRESHOLDS.retail_handling_noul) for item in items]
        exception_truth = [_as_bool(item.expected.get("expected_exception_needed")) for item in items]
        exception_pred = [_noul_decision(item, "exception_needed", DEFAULT_THRESHOLDS.retail_exception_noul) for item in items]
        route_truth = [str(item.expected.get("expected_route", "")) for item in items]
        route_pred = [item.route for item in items]
        route_labels = [label for label in ["accept", "review", "block", "error"] if label in route_truth or label in route_pred]
        handling_metrics = _binary_accuracy(risk_truth, risk_pred)
        exception_metrics = _binary_accuracy(exception_truth, exception_pred)
        warnings.append(
            "RETAIL_CODE_POLICY: estas métricas miden que el código reproduce el gold de política, no a Jev."
        )
        return {
            "domain": "retail",
            **stats,
            "series_decision_accuracy": _safe_div(sum(a == b for a, b in zip(decision_truth, decision_pred, strict=True)), len(items)),
            "handling_risk": handling_metrics,
            "handling_risk_accuracy": handling_metrics["accuracy"],
            "exception_needed": exception_metrics,
            "exception_needed_accuracy": exception_metrics["accuracy"],
            "series_decision": classification_metrics(decision_truth, decision_pred, decision_labels),
            "route_macro_f1": classification_metrics(route_truth, route_pred, route_labels)["macro_f1"],
            "route_confusion": classification_metrics(route_truth, route_pred, route_labels)["confusion"],
            "warnings": warnings,
        }

    area_truth = [str(item.expected.get("expected_area", "")) for item in items]
    area_pred = [_choice(item, "area") for item in items]
    intent_truth = [str(item.expected.get("expected_intent", "")) for item in items]
    intent_pred = [_choice(item, "intent") for item in items]
    urgency_labels = list(URGENCY_LABELS)
    urgency_truth = [str(item.expected.get("expected_urgency", "")) for item in items]
    urgency_pred = [_score_label(item, "urgency", urgency_labels) for item in items]
    human_truth = [_as_bool(item.expected.get("expected_human")) for item in items]
    human_pred = [_human_signal_composition(item) for item in items]
    security_truth = [_as_bool(item.expected.get("expected_security_legal")) for item in items]
    security_pred = [_noul_decision(item, "security_legal_risk", DEFAULT_THRESHOLDS.ticket_security_noul) for item in items]
    refund_truth = [_as_bool(item.expected.get("expected_refund")) for item in items]
    refund_pred = [_noul_decision(item, "refund_or_replacement", DEFAULT_THRESHOLDS.ticket_refund_noul) for item in items]
    technical_truth = [_as_bool(item.expected.get("expected_technical_repro")) for item in items]
    technical_pred = [_noul_decision(item, "technical_repro", DEFAULT_THRESHOLDS.ticket_technical_repro_review) for item in items]
    action_labels = list(ACTIONABILITY_LABELS)
    action_truth = [str(item.expected.get("expected_actionability", "")) for item in items]
    action_pred = [_choice(item, "actionability") for item in items]
    action_ordinal = _adjacent_accuracy(action_truth, action_pred, action_labels)
    route_truth = [str(item.expected.get("expected_route", "")) for item in items]
    route_pred = [item.route for item in items]
    area_labels = [label for label in ["tecnologia", "logistica", "ventas", "atencion_cliente", "pagos", "seguridad", "rrhh", "otro"] if label in area_truth or label in area_pred]
    intent_labels = [label for label in ["consulta", "incidencia", "reclamo", "solicitud", "retroalimentacion", "otro"] if label in intent_truth or label in intent_pred]
    route_labels = [label for label in ["accept", "review", "block", "error"] if label in route_truth or label in route_pred]
    route_metrics = classification_metrics(route_truth, route_pred, route_labels)
    human_metrics = _binary_accuracy(human_truth, human_pred)
    security_metrics = _binary_accuracy(security_truth, security_pred)
    refund_metrics = _binary_accuracy(refund_truth, refund_pred)
    technical_metrics = _binary_accuracy(technical_truth, technical_pred)
    gold_accept = _label_recall(route_truth, route_pred, "accept")
    return {
        "domain": "tickets",
        **stats,
        "area_accuracy": _safe_div(sum(a == b for a, b in zip(area_truth, area_pred, strict=True)), len(items)),
        "intent_accuracy": _safe_div(sum(a == b for a, b in zip(intent_truth, intent_pred, strict=True)), len(items)),
        "urgency_accuracy": _safe_div(sum(a == b for a, b in zip(urgency_truth, urgency_pred, strict=True)), len(items)),
        "area": classification_metrics(area_truth, area_pred, area_labels),
        "intent": classification_metrics(intent_truth, intent_pred, intent_labels),
        "urgency": classification_metrics(urgency_truth, urgency_pred, urgency_labels),
        "requires_human": human_metrics,
        "requires_human_accuracy": human_metrics["accuracy"],
        "security_legal": security_metrics,
        "security_legal_accuracy": security_metrics["accuracy"],
        "refund": refund_metrics,
        "refund_accuracy": refund_metrics["accuracy"],
        "technical_repro": technical_metrics,
        "technical_repro_accuracy": technical_metrics["accuracy"],
        "actionability": classification_metrics(action_truth, action_pred, [label for label in action_labels if label in action_truth or label in action_pred]),
        "actionability_accuracy": action_ordinal["accuracy"],
        "actionability_adjacent_accuracy": action_ordinal["adjacent_accuracy"],
        "actionability_mae": action_ordinal["mae"],
        "gold_accept_recall": gold_accept["recall"],
        "gold_accept": gold_accept,
        "route_macro_f1": route_metrics["macro_f1"],
        "route_confusion": route_metrics["confusion"],
        "warnings": warnings,
    }


def prompt_hash(domain: str) -> str:
    """Hash del contrato que se evalúa: política de código (retail) o prompts
    Jev + KB del state (tickets). El state entra al hash: hasta v6 no se
    hasheaba y un cambio de KB quedaba invisible para la trazabilidad."""
    if domain == "retail":
        encoded = json.dumps(RETAIL_POLICY, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
    questions = tickets_questions()
    payload = {
        "questions": {
            question_id: {
                "type": getattr(question, "type", None),
                "instructions": getattr(question, "instructions", None),
                "criteria": getattr(question, "criteria", None),
            }
            for question_id, question in questions.items()
        },
        "team_policy": TEAM_POLICY,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def state_schema_hash(domain: str) -> str | None:
    """Hash del state remoto (tickets): estructura + KB `team_policy`.

    Va en la metadata del evidence para poder decir si el state cambió
    respecto de una corrida congelada, separado del prompt.
    """
    if domain != "tickets":
        return None
    state = build_ticket_state({})
    encoded = json.dumps(state, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def threshold_hash(thresholds: RoutingThresholds = DEFAULT_THRESHOLDS) -> str:
    return hashlib.sha256(json.dumps(asdict(thresholds), sort_keys=True).encode("utf-8")).hexdigest()


def file_sha256(path: str | Path) -> str:
    """SHA-256 de un archivo con finales de línea normalizados a LF.

    Los hashes de la cadena (datasets, manifests) deben coincidir en
    cualquier SO: un checkout en Windows entrega CRLF y en Linux LF.
    """
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def dataset_hash(path: str | Path) -> str:
    return file_sha256(path)


def build_evidence(
    results: Iterable[RowResult],
    *,
    domain: str,
    input_path: str | Path,
    model: str,
    split: str = "holdout",
    thresholds: RoutingThresholds = DEFAULT_THRESHOLDS,
) -> dict[str, Any]:
    items = list(results)
    evaluated_at = datetime.now(timezone.utc).isoformat()
    metadata = {
        "domain": domain,
        "dataset": Path(input_path).name,
        "dataset_sha256": dataset_hash(input_path),
        "model": model,
        "prompt_sha256": prompt_hash(domain),
        "threshold_sha256": threshold_hash(thresholds),
        "split": split,
        "evaluated_at": evaluated_at,
        "mock": all(item.mock for item in items) if items else True,
        "backend": items[0].backend if items else None,
        "n": len(items),
    }
    schema_hash = state_schema_hash(domain)
    if schema_hash is not None:
        metadata["state_schema_sha256"] = schema_hash
    summary = evaluate_results(items, domain=domain, metadata=metadata)
    requests = []
    for item in items:
        requests.append({
            "row_id": item.row_id,
            "mock": item.mock,
            "model": model,
            "prompt_sha256": metadata["prompt_sha256"],
            "status": item.status,
            "expected": item.expected,
            "judgments": [judgment.to_dict() for judgment in item.judgments],
            "route": item.route,
            "reasons": item.reasons,
            "computed": item.computed,
            "latency_ms": item.latency_ms,
            "request_id": item.request_id,
            "error_code": item.error_code,
        })
    return {"metadata": metadata, "summary": summary, "warnings": summary.get("warnings", []), "requests": requests}


def write_evidence(payload: dict[str, Any], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def evaluate_file(path: str | Path, domain: str | None = None) -> dict[str, Any]:
    return evaluate_results(read_results(path), domain=domain)
