"""Tablero local de 3 minutos: fixtures, mock/live y evidencia."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from catalog_judge.aggregation import summarize_results
from catalog_judge.config import Settings
from catalog_judge.csv_io import normalize_retail_dataframe, normalize_tickets_dataframe, read_csv, results_to_dataframe
from catalog_judge.pipeline import execute_rows, make_backend
from catalog_judge.routing import DEFAULT_THRESHOLDS

ROOT = Path(__file__).resolve().parent
RETAIL_SAMPLE = ROOT / "retail" / "data" / "favorita_demand_96.csv"
TICKETS_SAMPLE = ROOT / "tickets" / "data" / "tickets_100.csv"
EVIDENCE_DIR = ROOT / "evaluations"

st.set_page_config(page_title="Catalog Judge", layout="wide")
st.title("Catalog Judge")
st.caption("Retail: política de demanda en código. Tickets: Jev sobre texto español. Mock de tickets no es evidencia.")
st.info(
    "Retail no envía filas a TypeSafe. En Tickets: mock prueba la interfaz; live requiere consentimiento y key."
)

retail_tab, tickets_tab, evidence_tab = st.tabs(["Retail", "Tickets", "Evidence / Report"])


def _read_upload(uploaded: Any, domain: str) -> list[dict[str, Any]]:
    frame = pd.read_csv(io.BytesIO(uploaded.getvalue()), dtype=str, keep_default_na=False)
    return normalize_retail_dataframe(frame) if domain == "retail" else normalize_tickets_dataframe(frame)


def _load_rows(domain: str, uploaded: Any) -> tuple[list[dict[str, Any]], str]:
    if uploaded is not None:
        return _read_upload(uploaded, domain), "upload opcional"
    path = RETAIL_SAMPLE if domain == "retail" else TICKETS_SAMPLE
    if not path.exists():
        st.error(f"Falta el fixture versionado: {path.name}")
        return [], "missing"
    return read_csv(path, domain), path.name


def _render_domain(domain: str, tab: Any) -> None:
    tab.header("Retail" if domain == "retail" else "Tickets")
    if domain == "retail":
        tab.caption("Triage de demanda: 96 series store_nbr × family. No hay SKUs, nombres, stock, costo ni margen. La política vive en código; Jev no re-deriva umbrales.")
    else:
        tab.caption("100 tickets públicos curados al español. Jev clasifica el texto; el código decide destino, prioridad y ruta.")
    uploaded = tab.file_uploader("Upload CSV opcional", type=["csv"], key=f"{domain}_upload")
    try:
        rows, source_name = _load_rows(domain, uploaded)
    except Exception as exc:
        tab.error(f"CSV inválido: {exc}")
        return
    if not rows:
        return
    with tab.expander("Preview del fixture versionado", expanded=False):
        preview_path = RETAIL_SAMPLE if domain == "retail" else TICKETS_SAMPLE
        if uploaded is None and preview_path.exists():
            tab.dataframe(pd.read_csv(preview_path, nrows=5), width="stretch", hide_index=True)
        else:
            tab.dataframe(pd.DataFrame(rows[:5]), width="stretch", hide_index=True)
    with tab.expander("Reglas del contrato", expanded=False):
        if domain == "retail":
            tab.write("Política de código: `series_decision`, `handling_risk`, `exception_needed` y `route` salen de `retail/policy.json`.")
            tab.caption("La caída es un proxy de demanda calculado en código; el dataset de Favorita no incluye stock.")
        else:
            tab.write("10 preguntas Jev: `area`, `intent`, `urgency`, `is_ambiguous`, `is_contradictory`, `needs_specialist`, `security_legal_risk`, `refund_or_replacement`, `actionability`, `technical_repro`.")
            tab.caption("Jev ve `ticket.subject` y `ticket.body`. El código decide destino, prioridad y ruta.")
    controls = tab.columns(3)
    if domain == "retail":
        mode = "code"
        controls[0].selectbox("Backend", ("code",), index=0, key=f"{domain}_mode")
        consent = False
        tab.caption("Retail usa la política versionada. No hay mock de Jev ni envío remoto.")
    else:
        mode = controls[0].selectbox("Backend", ("mock", "live"), index=0, key=f"{domain}_mode")
    limit = controls[1].number_input("Límite", min_value=1, max_value=len(rows), value=min(len(rows), 12), step=1, key=f"{domain}_limit")
    workers = controls[2].number_input("Workers", min_value=1, max_value=16, value=min(4, len(rows)), step=1, key=f"{domain}_workers")
    if domain == "tickets":
        if mode == "mock":
            tab.caption("Mock heurístico local: demuestra la interfaz; no es una medición de Jev.")
            consent = False
        else:
            tab.warning("Live enviará el state público a TypeSafe. Requiere consentimiento explícito y una key disponible en el entorno.")
            consent = tab.checkbox("Autorizo el envío de este fixture público a TypeSafe", key=f"{domain}_consent")
            if not consent:
                tab.info("El default seguro es mock; marca la autorización para live.")
                return
    tab.caption(
        "Thresholds de tickets congelados: "
        f"Choice review/accept {DEFAULT_THRESHOLDS.ticket_choice_review}/{DEFAULT_THRESHOLDS.ticket_choice_accept}; "
        f"destino sensible ≥ {DEFAULT_THRESHOLDS.ticket_choice_sensitive_accept}; "
        f"señales humanas ambiguo/contradicción/especialista "
        f"{DEFAULT_THRESHOLDS.ticket_ambiguous_noul}/{DEFAULT_THRESHOLDS.ticket_contradictory_noul}/{DEFAULT_THRESHOLDS.ticket_specialist_noul}; "
        f"security Noul {DEFAULT_THRESHOLDS.ticket_security_noul}; "
        f"actionability review < {DEFAULT_THRESHOLDS.ticket_actionability_review}; "
        f"urgency review ≥ nivel {int(DEFAULT_THRESHOLDS.ticket_urgency_high)}."
    )
    if not tab.button("Ejecutar demo", type="primary", key=f"{domain}_run"):
        return
    with st.spinner("Clasificando filas…"):
        try:
            backend = None if domain == "retail" else make_backend(mode, Settings.from_env(), allow_remote=consent)
            report = execute_rows(
                domain,
                rows,
                backend,
                workers=int(workers),
                limit=int(limit),
                mock=mode == "mock",
            )
        except Exception as exc:
            tab.error(f"No se pudo ejecutar: {exc}")
            return
    st.session_state[f"{domain}_report"] = report
    summary = summarize_results(report.results)
    tab.subheader("Resultado de ejecución")
    metric_cols = tab.columns(4)
    metric_cols[0].metric("Filas", summary["rows"])
    metric_cols[1].metric("Requests ok", summary["requests_completed"])
    metric_cols[2].metric("Review", summary["routes"].get("review", 0))
    metric_cols[3].metric("Contract coverage", f"{summary['contract_coverage']:.1%}")
    tab.caption("Contract coverage mide respuestas válidas del harness; no es accuracy ni calidad de Jev.")
    if domain == "retail":
        tab.write({
            "demand_drop_alert (proxy calculado)": summary.get("demand_drop_alerts", 0),
            "replenishment_candidate (proxy calculado)": summary.get("replenishment_candidates", 0),
        })
    else:
        tab.write({"destinos": summary.get("destinations", {}), "áreas": summary.get("areas", {})})
    frame = results_to_dataframe(report.results, include_text=False)
    route_filter = tab.multiselect("Filtrar rutas", sorted(frame["route"].dropna().unique()), key=f"{domain}_filter")
    filtered = frame if not route_filter else frame[frame["route"].isin(route_filter)]
    tab.dataframe(filtered, width="stretch", hide_index=True)
    if not filtered.empty:
        tab.download_button("CSV sin texto", filtered.to_csv(index=False).encode("utf-8"), file_name=f"{domain}_resultados.csv", mime="text/csv")
    tab.caption(f"Fuente: {source_name}; export sin texto de entrada.")


def _show_evidence_payload(tab: Any, label: str, payload: dict[str, Any]) -> None:
    summary = payload.get("summary", {})
    metadata = payload.get("metadata", {})
    tab.markdown(f"**{label}**")
    if metadata:
        tab.caption(
            f"n={metadata.get('n', summary.get('n', 0))} · model={metadata.get('model', '—')} · "
            f"mock={metadata.get('mock', '—')} · evaluado={metadata.get('evaluated_at', '—')}"
        )
    columns = tab.columns(5)
    columns[0].metric("Filas", summary.get("n", 0))
    columns[1].metric("Área", _percent(summary.get("area_accuracy")))
    columns[2].metric("Intent", _percent(summary.get("intent_accuracy")))
    columns[3].metric("Urgencia", _percent(summary.get("urgency_accuracy")))
    columns[4].metric("Route macro-F1", _percent(summary.get("route_macro_f1")))
    error_count = summary.get("error_count", len(summary.get("errors", {})))
    tab.caption(f"errores={error_count} · contract coverage={summary.get('contract_coverage', 0):.1%} (salud del harness, no calidad)")
    if payload.get("warnings") or summary.get("warnings"):
        tab.caption(" · ".join(str(item) for item in (payload.get("warnings") or summary.get("warnings", []))))
    with tab.expander("Detalle de métricas", expanded=False):
        tab.json(summary)


def _percent(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.1%}"
    except (TypeError, ValueError):
        return "—"


def _render_evidence(tab: Any) -> None:
    tab.header("Evidence / Report")
    tab.caption("Archivos de evaluación live reproducibles. No se muestra texto de terceros ni claves.")
    summary_path = EVIDENCE_DIR / "summary.json"
    if summary_path.exists():
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
        for run in payload.get("runs", []):
            _show_evidence_payload(tab, str(run.get("file", "run")), {"metadata": run.get("metadata", {}), "summary": run.get("summary", {})})
    else:
        tab.info("Todavía no hay summary live. El mock no se presenta como evidencia de Jev.")
    for filename, label in (("tickets_live_50.json", "Tickets confirmation (dev)"), ("retail_live_20.json", "Retail code policy")):
        path = EVIDENCE_DIR / filename
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            with tab.expander(label, expanded=False):
                _show_evidence_payload(tab, label, payload)
    uploaded = tab.file_uploader("Cargar evidence JSON local", type=["json"], key="evidence_upload")
    if uploaded is not None:
        try:
            _show_evidence_payload(tab, "Upload local", json.loads(uploaded.getvalue().decode("utf-8")))
        except Exception as exc:
            tab.error(f"JSON inválido: {exc}")


with retail_tab:
    _render_domain("retail", retail_tab)
with tickets_tab:
    _render_domain("tickets", tickets_tab)
with evidence_tab:
    _render_evidence(evidence_tab)
