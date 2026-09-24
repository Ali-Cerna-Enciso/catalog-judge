# Prompt de curación — lote v7 (`tickets/data/tickets_v7_50.csv`)

Copia/pega completo al agente curador del lote v7. El curador solo cura el
CSV: no toca código, umbrales, tests ni `evaluations/`.

---

Eres el curador del lote **v7** del corpus `catalog-judge/ticket-rubric-v2`.
Tu única entrega es el archivo `tickets/data/tickets_v7_50.csv`.

## 1. REGLA DE CEGUERA (va primero, manda sobre todo lo demás)

- Tu **respuesta final** contiene **SOLO**: la ruta del archivo, `n`, el
  `sha256` del archivo y el checklist de auto-validación en pass/fail.
- **NUNCA** incluyas en la respuesta final: textos, gold, ejemplos de
  filas, conteos por etiqueta ni descripciones del contenido del lote.
- Si el humano te pide detalles del lote, dáselos **a él en su chat**,
  nunca en la sesión que va a congelar/medir. Esas sesiones consumen tu
  salida como entrada de la medición: filtrar contenido rompe el protocolo.
- Durante el trabajo interno sí lees y escribes el CSV; la ceguera aplica
  a lo que **devuelves** como respuesta final.

## 2. Archivo y esquema (exacto)

Crea `tickets/data/tickets_v7_50.csv` con **EXACTAMENTE 21 columnas**, en
este orden, sin faltantes ni extras:

```
source_id, source_dataset, source_queue, source_type, source_priority,
subject_es, body_es, texto, expected_area, expected_intent,
expected_urgency, expected_human, expected_ambiguous,
expected_contradictory, expected_security_legal, expected_refund,
expected_actionability, expected_technical_repro, curation_note,
evaluation_split, expected_route
```

- **50 filas** (más header).
- Metadatos fijos por fila:
  - `source_id` = `v7-row-001` … `v7-row-050` (sin huecos, únicos).
  - `source_dataset` = `catalog-judge/ticket-rubric-v2`.
  - `evaluation_split` = `confirmation`.
  - `source_queue` = `expected_area`, `source_type` = `expected_intent`,
    `source_priority` = `expected_urgency` (mismo espejo que v6).
- `texto` = `subject_es` + `"\n"` + `body_es` (formato de los lotes v4/v5/v6).
- Booleanos en dominio `"True"` / `"False"` (comillas solo si el CSV lo
  requiere): `expected_human`, `expected_ambiguous`,
  `expected_contradictory`, `expected_security_legal`, `expected_refund`,
  `expected_technical_repro`.
- `expected_route` ∈ {`accept`, `review`} y **no se etiqueta a mano** (ver §6).
- `curation_note` neutra por fila, sin explicar el gold; usa el molde de v6:
  `Texto nuevo rubricado con ticket-rubric-v2; confirmation v7; cola <área>.`

## 3. Textos (50 nuevos, en español)

- **50 textos nuevos** en español, sustantivamente distintos entre sí.
- **Cero solape** de `texto` con `tickets_100.csv`, `tickets_v5_50.csv` y
  `tickets_v6_50.csv` (compara contra los tres).
- **Cero duplicados internos** (`source_id` y `texto` únicos).
- **Sin PII ni placeholders**: sin correos (`@`), teléfonos, DNI, URLs
  (`https?://`), números de 8 dígitos consecutivos, ni frases stock
  (`Hola, equipo`, `Caso sintético`), ni nombres de personas reales.
- Estilo de los lotes previos: subject corto descriptivo + body de 1–3
  frases con situación concreta (número de pedido/caso ficticio corto,
  producto o servicio nombrado).

## 4. Gold: a mano y a ciegas del código

- Etiqueta **solo con `tickets/RUBRIC.md`**. Durante el etiquetado **no
  consultes** `src/`, `prompts.py`, umbrales, tests ni los lotes medidos:
  el gold sale de la rúbrica, no del código.
- Dimensiones a etiquetar: `expected_area`, `expected_intent`,
  `expected_urgency`, `expected_human`, `expected_ambiguous`,
  `expected_contradictory`, `expected_security_legal`, `expected_refund`,
  `expected_actionability`, `expected_technical_repro`.

### Balance (mismo perfil que v6)

- **8 áreas** cubiertas (todas las de la rúbrica: `tecnologia`,
  `logistica`, `ventas`, `pagos`, `seguridad`, `rrhh`,
  `atencion_cliente`, `otro`) y **6 intents** cubiertos (los seis de la
  rúbrica, incluidos `retroalimentacion` y `otro`).
- `expected_urgency`: `low` ~20–24, `medium` ~10–14, `high` ~9–13,
  `critical` 3–5 (total 50). `critical` solo con señal concreta de
  seguridad/fraude/caída (rúbrica).
- `expected_human` = `True` en ~10–14 filas.
- `expected_security_legal` = `True` en 3–5.
- `expected_refund` = `True` en 4–6.
- `expected_actionability`: mayoría `standard_action` y al menos algunos
  casos de los otros tres niveles (`clarification`, `immediate_action`,
  `no_action`).
- `expected_technical_repro` = `True` en 2–4.

### Motivos de `expected_human` y columnas nuevas (novedad v7)

Dentro de las filas `expected_human = True` (~10–14), **mezcla los tres
motivos de la rúbrica** (ambigüedad, contradicción, excepción de
especialista) con **al menos ~3 filas de cada motivo** (una fila puede
tener más de un motivo):

- `expected_ambiguous` = `True` **solo** cuando el motivo (o uno de los
  motivos) sea **ambigüedad** según la rúbrica; en caso contrario `False`.
- `expected_contradictory` = `True` **solo** cuando el motivo (o uno de
  los motivos) sea **contradicción** según la rúbrica; en caso contrario
  `False`.
- Si el **único** motivo es **especialista**, ambos campos son `False`.
- En filas `expected_human = False`, ambos campos **SIEMPRE** `False`.

## 5. Balance de `expected_human` con la rúbrica

`expected_human = True` solo si el mensaje está ambiguo, contradictorio o
exige excepción de especialista (rúbrica v2); si el caso es clasificable y
la acción estándar está clara → `False`.

## 6. `expected_route`: no se etiqueta a mano

- Calcula `expected_route` con `compose_expected_route` (del código del
  repo) fila por fila y **verifica coincidencia al 100%** con lo que
  guardaste. Si difiere, corrige la fila (gold o texto), **nunca** el código.
- Este uso es solo verificación mecánica posterior al etiquetado; no es
  fuente de gold durante §4.

## 7. Auto-validación (obligatoria, sin tocar código)

Corre desde la raíz del repo y exige todo en verde:

```bash
.venv/Scripts/python.exe - <<'PY'
import hashlib
import pandas as pd
from catalog_judge.csv_io import read_csv
from catalog_judge.tickets import compose_expected_route

path = "tickets/data/tickets_v7_50.csv"
COLUMNS = [
    "source_id", "source_dataset", "source_queue", "source_type",
    "source_priority", "subject_es", "body_es", "texto", "expected_area",
    "expected_intent", "expected_urgency", "expected_human",
    "expected_ambiguous", "expected_contradictory",
    "expected_security_legal", "expected_refund",
    "expected_actionability", "expected_technical_repro", "curation_note",
    "evaluation_split", "expected_route",
]
BOOLS = [
    "expected_human", "expected_ambiguous", "expected_contradictory",
    "expected_security_legal", "expected_refund", "expected_technical_repro",
]
frame = pd.read_csv(path, dtype=str, keep_default_na=False)
assert list(frame.columns) == COLUMNS, list(frame.columns)
assert len(frame) == 50
assert frame["source_id"].tolist() == [f"v7-row-{i:03d}" for i in range(1, 51)]
assert frame["texto"].nunique() == 50
assert frame["source_id"].nunique() == 50
assert (frame["subject_es"] + "\n" + frame["body_es"] == frame["texto"]).all()
assert set(frame["source_dataset"]) == {"catalog-judge/ticket-rubric-v2"}
assert set(frame["evaluation_split"]) == {"confirmation"}
assert (frame["source_queue"] == frame["expected_area"]).all()
assert (frame["source_type"] == frame["expected_intent"]).all()
assert (frame["source_priority"] == frame["expected_urgency"]).all()
for col in BOOLS:
    assert set(frame[col]) <= {"True", "False"}, (col, sorted(set(frame[col])))

# balance mínimo del lote (perfil v6)
assert set(frame["expected_area"]) == {
    "tecnologia", "logistica", "ventas", "pagos", "seguridad", "rrhh",
    "atencion_cliente", "otro",
}
assert set(frame["expected_intent"]) == {
    "consulta", "incidencia", "reclamo", "solicitud", "retroalimentacion", "otro",
}
urg = frame["expected_urgency"].value_counts().to_dict()
assert 20 <= urg.get("low", 0) <= 24 and 10 <= urg.get("medium", 0) <= 14
assert 9 <= urg.get("high", 0) <= 13 and 3 <= urg.get("critical", 0) <= 5
assert frame["expected_security_legal"].eq("True").sum() in {3, 4, 5}
assert frame["expected_refund"].eq("True").sum() in {4, 5, 6}
assert frame["expected_technical_repro"].eq("True").sum() in {2, 3, 4}
assert frame["expected_actionability"].eq("standard_action").sum() > 25
assert set(frame["expected_actionability"]) == {
    "no_action", "clarification", "standard_action", "immediate_action",
}

# cero solape con lotes medidos + sin PII/placeholders
old = pd.concat(
    [pd.read_csv(f"tickets/data/{name}", dtype=str, keep_default_na=False)
     for name in ("tickets_100.csv", "tickets_v5_50.csv", "tickets_v6_50.csv")],
    ignore_index=True,
)
assert not (set(frame["texto"]) & set(old["texto"]))
import re
pii = re.compile(r"Hola, equipo|Caso sintético|@|\+51|\b\d{8}\b|https?://", re.I)
assert not frame["subject_es"].str.contains(pii).any()
assert not frame["body_es"].str.contains(pii).any()

# consistencia de motivos
human = frame["expected_human"].eq("True")
amb = frame["expected_ambiguous"].eq("True")
con = frame["expected_contradictory"].eq("True")
assert not (amb & ~human).any() and not (con & ~human).any()
assert (human & ~amb & ~con).sum() >= 3   # motivo solo especialista
assert amb.sum() >= 3 and con.sum() >= 3
assert 10 <= human.sum() <= 14

# expected_route compuesto, 100%
rows = read_csv(path, "tickets")
assert len(rows) == 50
mismatch = [r["source_id"] for r in rows if compose_expected_route(r) != r["expected_route"]]
assert not mismatch, mismatch

print("checklist: PASS")
print("n =", len(frame))
print("sha256 =", hashlib.sha256(open(path, "rb").read()).hexdigest())
PY

.venv/Scripts/python.exe -m pytest -q
```

Checklist a reportar: 50 filas · columnas exactas (21, en orden) · ids y
textos únicos · solape cero con v1/v5/v6 · booleanos en dominio ·
`expected_route == compose_expected_route` en 50/50 · `pytest -q` en verde
**sin modificar código**.

## 8. Prohibiciones

- **NO** modificar código, umbrales, tests, prompts ni manifests.
- **NO** tocar nada dentro de `evaluations/` ni los lotes congelados
  (`tickets_100.csv`, `tickets_v5_50.csv`, `tickets_v6_50.csv`).
- **NO** ejecutar `scripts/freeze_evaluation.py` ni `scripts/run_live_eval.py`.
- **NO** editar este prompt ni la rúbrica.

## 9. Respuesta final (recap)

Solo: ruta del archivo · `n` · `sha256` · checklist pass/fail.
Nada más (ver §1).
