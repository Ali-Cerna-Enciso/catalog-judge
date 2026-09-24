"""Diagnóstico post-hoc de la corrida live v4 (50 tickets, jev-1.13.0).

Este script NO es una métrica honesta: lee el confirmation `dev` ya gastado
para entender DÓNDE se pierde el route macro-F1 (0.55) y qué palancas reales
existen. Cualquier número de "umbral re-simulado" de aquí es overfit
diagnóstico y no puede presentarse como resultado de v4 ni v5.

Salida: informe.md en esta misma carpeta.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "evaluations" / "tickets_live_50.json"
CSV_PATH = ROOT / "tickets" / "data" / "tickets_100.csv"
OUT = Path(__file__).resolve().parent / "informe.md"


def load_rows() -> dict[str, dict[str, str]]:
    with CSV_PATH.open(encoding="utf-8", newline="") as handle:
        return {row["source_id"]: row for row in csv.DictReader(handle)}


def jmap(request: dict) -> dict[str, dict]:
    return {item["question_id"]: item for item in request.get("judgments", [])}


def macro_f1(truth: list[str], pred: list[str], labels: list[str]) -> float:
    scores = []
    for label in labels:
        tp = sum(t == label and p == label for t, p in zip(truth, pred, strict=True))
        fp = sum(t != label and p == label for t, p in zip(truth, pred, strict=True))
        fn = sum(t == label and p != label for t, p in zip(truth, pred, strict=True))
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        scores.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    return sum(scores) / len(scores) if scores else 0.0


def main() -> None:
    payload = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    requests = payload["requests"]
    rows = load_rows()

    lines: list[str] = []
    add = lines.append

    add("# Diagnóstico post-hoc del protocolo v4 — dev (50 tickets, jev-1.13.0)")
    add("")
    add("> **Qué es**: análisis de las evidencias ya publicadas")
    add("> (`evaluations/tickets_live_50.json`) para explicar el route macro-F1 0.55.")
    add("> Es *post-hoc*: usa el split `dev` ya gastado como confirmation.")
    add('> Los cortes "re-simulados" de la sección 8 son overfit de diagnóstico:')
    add("> sirven para elegir el diseño de v5 (lote nuevo), **no** para reportar una")
    add("> mejora de v4. Volver a correr un prompt tuneado sobre estas 50 filas = el")
    add("> truco de v3.1.")
    add(">")
    add("> Reproducir (sin key ni red; regenera este archivo):")
    add("> `.venv/Scripts/python.exe docs/protocol_v4_diagnostico/diagnostico.py`")
    add("")
    add("## 0. Hallazgos")
    add("")
    add("1. **El route F1 no lo rompen los 5 `accept→review` sino los 16**")
    add("   **`review→accept`**: precisión de `accept` 21/37 = 0.57.")
    add("2. **`expected_route` es casi una función de otras columnas del gold**:")
    add("   `human OR clarification OR urgency in (high,critical)` reproduce 49/50")
    add("   (`human=True` solo: 46/50, y 20/20 de `human=True` caen en `review`).")
    add("   El route mide la alineación entre la rúbrica de Jev y la de la")
    add("   curación, no la capacidad del modelo.")
    add("3. **`actionability` está colapsado**: 47/50 en el nivel 1; promedios")
    add("   1.13 / 1.13 / 1.23 por clase gold → el Score no separa ninguna clase")
    add("   (sección 6). El `focus` ancla al nivel 1 y los `examples` están en")
    add("   inglés sobre un corpus en español.")
    add("4. **Contradicciones instructions/criteria** (jaggedness 1.13 #7):")
    add("   `reclamo` acepta *seeks compensation* mientras `solicitud.not_for`")
    add("   dice que un pedido neutral de reembolso es `solicitud` (recall de")
    add("   `reclamo` 0.25, sección 12); `otro` prohíbe ser *fallback* mientras el")
    add("   gold usa `otro` para consultas genéricas (F1 0, sección 11).")
    add("5. **`requires_human` (0.64) tiene solape real de definición**: el gold no")
    add("   tiene rúbrica escrita; con corte 0.50 sube a 0.70 (sección 5).")
    add("6. **La confidence de Jev sí predice**: accuracy 0.89/0.95 en la banda")
    add("   [0.9,1] contra 0.40/0.60 en [0.5,0.75) (sección 4), y el piso actual")
    add("   de Choice (0.50) está bajo el piso documentado (0.60).")
    add("7. **`urgency`**: el gold nunca marca `critical` (support 0) pero el")
    add("   Score tiene nivel 3 → 2 errores gratuitos; `medium→low` 9/18")
    add("   (sección 7).")
    add("")

    # ------------------------------------------------------------------
    # 1. Regla real detrás de expected_route (¿el gold route es función de
    #    los expected_* como en retail?)
    # ------------------------------------------------------------------
    add("## 1. ¿De qué depende `expected_route` en el gold?")
    add("")
    rule_fields = ["expected_human", "expected_security_legal", "expected_refund",
                   "expected_actionability", "expected_urgency", "expected_technical_repro"]
    combos_review: Counter = Counter()
    combos_accept: Counter = Counter()
    for request in requests:
        exp = request["expected"]
        key = tuple(f"{f}={exp.get(f)}" for f in rule_fields if exp.get(f) in (True, "clarification", "high", "critical") or f in ("expected_human", "expected_actionability"))
        if exp.get("expected_route") == "review":
            combos_review[key] += 1
        else:
            combos_accept[key] += 1

    # Prueba de reglas candidatas simples
    def candidate_rules() -> dict[str, callable]:
        def r_human_or_action(r):
            e = r["expected"]
            return e.get("expected_human") is True or e.get("expected_actionability") == "clarification"

        def r_human_only(r):
            return r["expected"].get("expected_human") is True

        def r_action_only(r):
            return r["expected"].get("expected_actionability") == "clarification"

        def r_human_action_or_high(r):
            e = r["expected"]
            return (e.get("expected_human") is True
                    or e.get("expected_actionability") == "clarification"
                    or e.get("expected_urgency") in ("high", "critical"))

        def r_human_or_high(r):
            e = r["expected"]
            return e.get("expected_human") is True or e.get("expected_urgency") in ("high", "critical")

        return {
            "human==True OR actionability==clarification": r_human_or_action,
            "human==True": r_human_only,
            "actionability==clarification": r_action_only,
            "human OR actionability==clarification OR urgency in (high,critical)": r_human_action_or_high,
            "human OR urgency in (high,critical)": r_human_or_high,
        }

    add("| Regla candidata sobre `expected_*` | Coincide con `expected_route` |")
    add("|---|---:|")
    n = len(requests)
    for name, fn in candidate_rules().items():
        hits = sum(bool(fn(r)) == (r["expected"].get("expected_route") == "review") for r in requests)
        add(f"| `{name}` | {hits}/{n} |")
    add("")

    # Desglose: por qué cada gold=review
    reasons_gold: Counter = Counter()
    for request in requests:
        e = request["expected"]
        if e.get("expected_route") != "review":
            continue
        why = []
        if e.get("expected_human") is True:
            why.append("human")
        if e.get("expected_actionability") == "clarification":
            why.append("action_clarif")
        if e.get("expected_urgency") in ("high", "critical"):
            why.append("urg_high")
        if e.get("expected_security_legal") is True:
            why.append("sec")
        reasons_gold["+".join(why) or "sin_señal"] += 1
    add("**Por qué el gold marca `review` (n=24):**")
    add("")
    for key, count in reasons_gold.most_common():
        add(f"- `{key}`: {count}")
    add("")

    # ------------------------------------------------------------------
    # 2. Route: las 50 filas con señales
    # ------------------------------------------------------------------
    add("## 2. Route: qué pasó fila por fila")
    add("")
    tp = fp = fn = tn = 0
    add("| row | gold | pred | human noul | act score | urg score | conf area | conf intent | reasons |")
    add("|---|---|---|---:|---:|---:|---:|---:|---|")
    fn_rows, fp_rows = [], []
    for request in requests:
        j = jmap(request)
        gold = request["expected"].get("expected_route", "")
        pred = request.get("route", "")
        if gold == "accept" and pred == "accept":
            tp += 1
        elif gold == "review" and pred == "review":
            tn += 1
        elif gold == "review" and pred == "accept":
            fp += 1
            fn_rows.append(request)
        else:
            fn += 1
            fp_rows.append(request)
        add("| {rid} | {gold} | {pred} | {hum:.2f} | {act:.2f} | {urg:.2f} | {ca:.2f} | {ci:.2f} | {reasons} |".format(
            rid=request["row_id"], gold=gold, pred=pred,
            hum=j["requires_human"]["noul"], act=j["actionability"]["score"],
            urg=j["urgency"]["score"], ca=j["area"].get("confidence", 0),
            ci=j["intent"].get("confidence", 0),
            reasons="; ".join(request.get("reasons", []))[:80],
        ))
    add("")
    add(f"- gold=review → pred=accept (falsos accept): **{fp}**")
    add(f"- gold=accept → pred=review (falsos review): **{fn}**")
    add(f"- TP accept: {tp} · TN review: {tn}")
    add("")

    # ------------------------------------------------------------------
    # 3. Las filas gold=review que Jev/código dejó pasar (el verdadero agujero)
    # ------------------------------------------------------------------
    add("## 3. Las 16 filas `review` que el código aprobó")
    add("")
    add("El route F1 no lo matan los 5 accept→review; lo matan los falsos accept.")
    add("")
    add("| row | texto (preview) | gold reasons esperados | human | act | urg | conf a/i | predicho |")
    add("|---|---|---|---:|---:|---:|---|---|")
    for request in fn_rows:
        j = jmap(request)
        row = rows.get(request["row_id"], {})
        text = (row.get("subject_es", "") + " — " + row.get("body_es", ""))[:90]
        e = request["expected"]
        gold_why = []
        if e.get("expected_human") is True:
            gold_why.append("human")
        if e.get("expected_actionability") == "clarification":
            gold_why.append("act_clarif")
        if e.get("expected_urgency") in ("high", "critical"):
            gold_why.append("urg_high")
        add("| {rid} | {text} | {why} | {hum:.2f} | {act:.2f} | {urg:.2f} | {ca:.2f}/{ci:.2f} | {route} |".format(
            rid=request["row_id"], text=text, why="+".join(gold_why) or "-",
            hum=j["requires_human"]["noul"], act=j["actionability"]["score"],
            urg=j["urgency"]["score"], ca=j["area"].get("confidence", 0),
            ci=j["intent"].get("confidence", 0), route=request["route"],
        ))
    add("")

    # ------------------------------------------------------------------
    # 4. Calibración confidence (área/intent) por banda
    # ------------------------------------------------------------------
    add("## 4. ¿Sirve la confidence de Jev? (accuracy por banda)")
    add("")
    bands = [(0.0, 0.5), (0.5, 0.75), (0.75, 0.9), (0.9, 1.01)]
    for qid, exp_key in (("area", "expected_area"), ("intent", "expected_intent")):
        add(f"### {qid}")
        add("")
        add("| banda confidence | n | accuracy |")
        add("|---|---:|---:|")
        for low, high in bands:
            sel = [r for r in requests
                   if low <= jmap(r)[qid].get("confidence", 0) < high]
            if not sel:
                continue
            hits = sum(jmap(r)[qid].get("choice") == r["expected"].get(exp_key) for r in sel)
            add(f"| [{low}, {high}) | {len(sel)} | {hits/len(sel):.2f} |")
        add("")

    # ------------------------------------------------------------------
    # 5. requires_human: distribución de noul vs gold
    # ------------------------------------------------------------------
    add("## 5. `requires_human` (accuracy 0.64) — ¿dónde está el corte óptimo?")
    add("")
    for gold_value, name in ((True, "gold human=True"), (False, "gold human=False")):
        values = sorted(jmap(r)["requires_human"]["noul"] for r in requests
                        if r["expected"].get("expected_human") is gold_value)
        add(f"- **{name}** (n={len(values)}): " + ", ".join(f"{v:.2f}" for v in values))
    add("")
    add("| corte noul | TP | FP | TN | FN | accuracy |")
    add("|---:|---:|---:|---:|---:|---:|")
    for cut in (0.30, 0.40, 0.50, 0.60, 0.65, 0.70, 0.85):
        tp_ = fp_ = tn_ = fn_ = 0
        for r in requests:
            gold = r["expected"].get("expected_human") is True
            pred = jmap(r)["requires_human"]["noul"] >= cut
            if gold and pred:
                tp_ += 1
            elif not gold and pred:
                fp_ += 1
            elif not gold and not pred:
                tn_ += 1
            else:
                fn_ += 1
        acc = (tp_ + tn_) / len(requests)
        add(f"| {cut:.2f} | {tp_} | {fp_} | {tn_} | {fn_} | {acc:.2f} |")
    add("")

    # ------------------------------------------------------------------
    # 6. actionability: sesgo del Score
    # ------------------------------------------------------------------
    add("## 6. `actionability` — el Score se queda pegado en el nivel 1")
    add("")
    dist = defaultdict(Counter)
    raw = defaultdict(list)
    for r in requests:
        gold = r["expected"].get("expected_actionability", "")
        score = jmap(r)["actionability"]["score"]
        dist[gold][round(score)] += 1
        raw[gold].append(score)
    add("| gold | n | score promedio | distribución (0/1/2/3) |")
    add("|---|---:|---:|---|")
    for gold in ("no_action", "clarification", "standard_action", "immediate_action"):
        if gold not in dist:
            continue
        counts = [dist[gold].get(i, 0) for i in range(4)]
        add(f"| {gold} | {sum(counts)} | {sum(raw[gold])/len(raw[gold]):.2f} | {'/'.join(str(c) for c in counts)} |")
    add("")

    # ------------------------------------------------------------------
    # 7. urgency: score crudo por gold
    # ------------------------------------------------------------------
    add("## 7. `urgency` (accuracy 0.66) — score crudo por clase gold")
    add("")
    urg_raw: dict[str, list[float]] = defaultdict(list)
    for r in requests:
        urg_raw[r["expected"].get("expected_urgency", "")].append(jmap(r)["urgency"]["score"])
    add("| gold | n | score promedio | min | max |")
    add("|---|---:|---:|---:|---:|")
    for gold in ("low", "medium", "high", "critical"):
        if gold not in urg_raw:
            continue
        vals = urg_raw[gold]
        add(f"| {gold} | {len(vals)} | {sum(vals)/len(vals):.2f} | {min(vals):.2f} | {max(vals):.2f} |")
    add("")

    # ------------------------------------------------------------------
    # 8. Re-simulación de route con distintas palancas (SOLO diagnóstico)
    # ------------------------------------------------------------------
    add("## 8. Re-simulación de route (overfit de diagnóstico, NO resultado)")
    add("")
    truth = [r["expected"].get("expected_route", "") for r in requests]

    def simulate(rule) -> tuple[float, float, float]:
        pred = []
        for r in requests:
            j = jmap(r)
            pred.append("review" if rule(r, j) else "accept")
        return macro_f1(truth, pred, ["accept", "review"]), pred.count("accept"), pred.count("review")

    variants = {
        "v4 actual": lambda r, j: r["route"] == "review",
        "v4 + human>=0.50 → review": lambda r, j: r["route"] == "review" or j["requires_human"]["noul"] >= 0.50,
        "v4 + actionability<=1 → review": lambda r, j: r["route"] == "review" or j["actionability"]["score"] <= 1.0,
        "v4 + urgency>=2 → review (ya está) + human>=0.50": lambda r, j: r["route"] == "review" or j["requires_human"]["noul"] >= 0.50,
        "v4 + conf(area/intent)<0.75 → review": lambda r, j: r["route"] == "review" or j["area"].get("confidence", 1) < 0.75 or j["intent"].get("confidence", 1) < 0.75,
        "v4 + actionability<=1 O human>=0.50": lambda r, j: r["route"] == "review" or j["actionability"]["score"] <= 1.0 or j["requires_human"]["noul"] >= 0.50,
        "solo expected_* (oracle señales del gold)": lambda r, j: (r["expected"].get("expected_human") is True
                                                                  or r["expected"].get("expected_actionability") == "clarification"),
    }
    add("| Variante | route macro-F1 | #accept | #review |")
    add("|---|---:|---:|---:|")
    for name, rule in variants.items():
        f1, n_acc, n_rev = simulate(rule)
        add(f"| {name} | {f1:.3f} | {n_acc} | {n_rev} |")
    add("")

    add("## 9. Techo: si las predicciones de señales fueran perfectas")
    add("")
    pred_perfect = ["review" if (r["expected"].get("expected_human") is True
                                 or r["expected"].get("expected_actionability") == "clarification")
                    else "accept" for r in requests]
    add(f"- route F1 con `expected_human`/`expected_actionability` perfectos: "
        f"{macro_f1(truth, pred_perfect, ['accept', 'review']):.3f}")
    add("- → el route F1 depende casi totalmente de `requires_human` (0.64) y "
        "`actionability` (0.28 exacto): **ahí está el trabajo de v5**.")
    add("")

    # ------------------------------------------------------------------
    # 10. Las 5 filas gold=accept que el código mandó a review
    # ------------------------------------------------------------------
    add("## 10. Las 5 filas `accept` que el código vetó (falsos review)")
    add("")
    add("| row | texto (preview) | reason del veto | area conf | intent conf | act |")
    add("|---|---|---|---:|---:|---:|")
    for request in fp_rows:
        j = jmap(request)
        row = rows.get(request["row_id"], {})
        text = (row.get("subject_es", "") + " — " + row.get("body_es", ""))[:80]
        reasons = [r for r in request.get("reasons", [])
                   if "confidence" in r or "actionability" in r]
        add(f"| {request['row_id']} | {text} | {'; '.join(reasons)[:70]} | "
            f"{j['area'].get('confidence', 0):.2f} | {j['intent'].get('confidence', 0):.2f} | "
            f"{j['actionability']['score']:.2f} |")
    add("")

    # ------------------------------------------------------------------
    # 11. Gold `otro` (área): ¿por qué Jev nunca lo elige?
    # ------------------------------------------------------------------
    add("## 11. Área `otro` en el gold (F1 = 0) — textos y predicción")
    add("")
    for request in requests:
        if request["expected"].get("expected_area") != "otro":
            continue
        j = jmap(request)
        row = rows.get(request["row_id"], {})
        text = (row.get("subject_es", "") + " — " + row.get("body_es", ""))[:95]
        add(f"- `{request['row_id']}` → predicho **{j['area'].get('choice')}** "
            f"(conf {j['area'].get('confidence', 0):.2f}): {text}")
    add("")

    # ------------------------------------------------------------------
    # 12. Gold `reclamo` (recall 0.25): textos y predicción
    # ------------------------------------------------------------------
    add("## 12. Intento `reclamo` en el gold (recall 0.25) — textos y predicción")
    add("")
    for request in requests:
        if request["expected"].get("expected_intent") != "reclamo":
            continue
        j = jmap(request)
        row = rows.get(request["row_id"], {})
        text = (row.get("subject_es", "") + " — " + row.get("body_es", ""))[:95]
        add(f"- `{request['row_id']}` → predicho **{j['intent'].get('choice')}** "
            f"(conf {j['intent'].get('confidence', 0):.2f}): {text}")
    add("")

    # ------------------------------------------------------------------
    # 13. requires_human: el solape entre clases
    # ------------------------------------------------------------------
    add("## 13. `requires_human`: dónde se cruzan las clases (con texto)")
    add("")
    add("Gold=**True** con noul baja (Jev dice 'no hace humano'):")
    add("")
    for request in sorted(requests, key=lambda r: jmap(r)["requires_human"]["noul"]):
        j = jmap(request)
        if request["expected"].get("expected_human") is not True or j["requires_human"]["noul"] >= 0.50:
            continue
        row = rows.get(request["row_id"], {})
        text = (row.get("subject_es", "") + " — " + row.get("body_es", ""))[:85]
        add(f"- noul {j['requires_human']['noul']:.2f} `{request['row_id']}`: {text}")
    add("")
    add("Gold=**False** con noul alta (Jev dice 'sí humano'):")
    add("")
    for request in sorted(requests, key=lambda r: -jmap(r)["requires_human"]["noul"]):
        j = jmap(request)
        if request["expected"].get("expected_human") is not False or j["requires_human"]["noul"] < 0.50:
            continue
        row = rows.get(request["row_id"], {})
        text = (row.get("subject_es", "") + " — " + row.get("body_es", ""))[:85]
        add(f"- noul {j['requires_human']['noul']:.2f} `{request['row_id']}`: {text}")
    add("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"informe escrito en {OUT}")


if __name__ == "__main__":
    main()
