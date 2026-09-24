# Evidencia de evaluación

Esta carpeta contiene exports de corridas autorizadas. El mock de tickets no
se guarda aquí como evidencia de Jev. Retail no llama a Jev.

## Protocolo v7

- Tickets: `jev-1.13.0`, 1 llamada por fila, confirmation = 50 textos
  **nuevos** (`tickets/data/tickets_v7_50.csv`), rúbrica v2.
- Contrato: 10 preguntas. Corte `is_ambiguous` **0.85** (candidato post-hoc
  de v6; una sola medición, sin retuning).
- Gold: columnas `expected_ambiguous` / `expected_contradictory`.
- `expected_route` lo compone el mismo `routing.py` que la predicción.
- State live: `{"ticket": {"subject", "body"}, "team_policy": ...}`.
- Retail: igual que v4 (código).
- No se re-miden v4 / v5 / v6.

## Archivos esperados

- `tickets_live_50.json` — confirmation Jev v7
- `retail_live_20.json` — política de código (re-encadenada al manifest v7)
- `summary.json`
- `holdout_manifest.json`

Historia: `archive/protocol_v6/` (F1 0.63, corte 0.70),
`archive/protocol_v5/` (F1 0.72), `archive/protocol_v4/` (F1 0.55),
`archive/protocol_v3.1/`, `archive/protocol_v1/`.

Los hashes de la cadena (`datasets[].sha256`, `holdout_manifest_sha256`)
se calculan con finales de línea normalizados a LF (`file_sha256`), para
que la cadena verifique igual en Windows (CRLF) y en Linux (LF).

Diagnóstico v6: sección más abajo. Diagnóstico v4:
[`docs/protocol_v4_diagnostico/informe.md`](../docs/protocol_v4_diagnostico/informe.md).


## Métricas

Tickets: `area_accuracy`, `intent_accuracy`, `urgency_accuracy`, binarios
Noul, `actionability_adjacent_accuracy` (ordinal, no exact-match como
headline), `gold_accept_recall`, `route_macro_f1`.

Retail: reproducción de `series_decision` / handling / exception / route.

Los splits son pequeños; sirven para reproducibilidad, no como benchmark
de producción.

## Resultados del protocolo v7

Confirmation congelada **antes** de live. 50 textos nuevos. Un solo live.
No se retocó el prompt ni el corte 0.85 después de ver las cifras.

| Dominio | Split | n | Válidas / errores | Rutas | Headline | Route macro-F1 | Latencia |
|---|---|---:|---:|---|---|---:|---:|
| Tickets (Jev 1.13.0) | `confirmation` v7 | 50 | 50 / 0 | 13 accept / 37 review | área 0.88 · intent 0.86 · urgencia 0.72 · humano 0.98 · seguridad 1.00 · refund 1.00 · repro 0.98 · actionability 0.66 / adyacente 0.88 · gold-accept 13/21 | **0.82** | 611 ms |
| Retail (código) | `holdout` | 20 | 20 / 0 | 3 accept / 16 review / 1 block | series_decision 1.00 · handling 1.00 · excepción 1.00 | 1.00 | <1 ms |

Matriz de ruta v7: gold accept 13/8; gold review 0/29. Cero `review→accept`.
Quedan 8 `accept→review` (fail-closed). No hay sweep ni retuning sobre este lote.

v6 (F1 0.63, corte 0.70): `archive/protocol_v6/`.
v5 (F1 0.72): `archive/protocol_v5/`.
v4 (F1 0.55): `archive/protocol_v4/`.

## Resultados del protocolo v5

Confirmation congelada **antes** de live. 50 textos nuevos. No se retocó el prompt después.

| Dominio | Split | n | Válidas / errores | Rutas | Headline | Route macro-F1 | Latencia |
|---|---|---:|---:|---|---|---:|---:|
| Tickets (Jev 1.13.0) | `confirmation` v5 | 50 | 50 / 0 | 25 accept / 25 review | área 0.88 · intent 0.76 · urgencia 0.70 · humano 0.78 · seguridad 1.00 · refund 0.92 · repro 0.98 · actionability 0.42 / adyacente 1.00 · gold-accept 19/27 | **0.72** | 3270 ms |
| Retail (código) | `holdout` | 20 | 20 / 0 | 3 accept / 16 review / 1 block | series_decision 1.00 · handling 1.00 · excepción 1.00 | 1.00 | <1 ms |

Matriz de ruta: gold accept 19/8; gold review 6/17. El agujero v4 (16 review→accept) baja a 6.

## Resultados del protocolo v6

Un solo live (50 filas nuevas `tickets_v6_50.csv`, contrato 10 preguntas),
sin retuning post-hoc.

| Dominio | Split | n | Válidas / errores | Rutas | Headline | Route macro-F1 | Latencia |
|---|---|---:|---:|---|---|---:|---:|
| Tickets (Jev 1.13.0) | `confirmation` v6 | 50 | 50 / 0 | 9 accept / 41 review | área 0.86 · intent 0.80 · urgencia 0.72 · humano 0.72 · seguridad 0.98 · refund 1.00 · repro 0.98 · actionability 0.52 / adyacente 0.96 · gold-accept 8/23 | **0.63** | 670 ms |
| Retail (código) | `holdout` | 20 | 20 / 0 | — | series_decision 1.00 | 1.00 | <1 ms |

Matriz de ruta v6: gold accept 8/15; gold review 1/26. El sistema sobre-revisa
en lote fresco: 15 `accept→review` (9 por `is_ambiguous.noul ≥ 0.70`, 3 por
`urgency.nivel ≥ 2`, 3 por `intent.confidence_bajo`, 1 por destino sensible
0.85, 1 por `no_action`) contra un solo `review→accept`. Se reporta sin tocar
umbrales: cualquier respuesta al sobre-review es protocolo v7 en lote nuevo.

v4 (F1 0.55): `archive/protocol_v4/`. Diagnóstico:
[`docs/protocol_v4_diagnostico/informe.md`](../docs/protocol_v4_diagnostico/informe.md).

## Protocolo v6 (medido 2026-09-23: un solo live, lote nuevo)

Seis palancas de Jev, cinco implementadas y una documentada:

1. `requires_human` fragmentado en 3 Noul atómicos (`is_ambiguous` 0.70,
   `is_contradictory` 0.50, `needs_specialist` 0.50); composición OR con
   razón nombrada por señal.
2. Nivel modal de urgency unificado (`modal_level`): argmax de
   `probabilities`, fallback `round(score)`; lo comparten ruta, prioridad
   y evaluación (corrige `round` vs `>= 2.0` continuo de v5).
3. KB `team_policy` en el state (qué ejecuta el equipo sin pedir más
   datos); entra al `prompt_hash` y al `state_schema_sha256` del evidence.
4. Confidence por acción: destinos sensibles (`seguridad`, `pagos`)
   exigen `area.confidence ≥ 0.85`; resto 0.60/0.75.
5. Runner-up/margen de `area` desde `probabilities` en `computed`
   (`area_runner_up`, `area_margin`); auditoría sin veto.
6. CatBoost **documentado, no implementado**: entrenar un reranker sobre
   judgments/`probabilities` requiere cientos de filas etiquetadas con el
   contrato v6; con 50 filas por lote no hay soporte. Se evalúa recién
   cuando el lote v6 (o acumulado posterior) lo permita.

Protocolo honesto: no se re-miden las 50 filas de v4 ni las 50 de v5
(quemadas). Cualquier cambio de contrato/umbrales es v6 y se mide en lote
nuevo con un solo live y sin retuning post-hoc. El gold de filas viejas
es estable por fallback (`needs_specialist = expected_human`).

## Diagnóstico v6: por qué el F1 bajó (solo análisis, sin retuning)

Todo lo que sigue es **análisis**, no resultado medido: se calculó offline
sobre el evidence congelado `evaluations/tickets_live_50.json`, sin nuevo
live, sin re-medición y sin aplicar ningún cambio al lote v6. Ni la
ablation ni el sweep son métricas oficiales; el único número oficial de v6
es el route macro-F1 **0.6324** (vs **0.7196** de v5) de la tabla anterior.

### 1. No es el lote ni el modelo

El gold de v5 y v6 tiene dificultad casi idéntica:

| Dimensión gold | v5 | v6 |
|---|---|---|
| `expected_human` | 38 False / 12 True | 38 False / 12 True |
| `urgency` | 23 low / 12 medium / 11 high / 4 critical | 23 / 13 / 10 / 4 |
| `actionability` | 36 standard / 6 clarification / 5 immediate / 3 no_action | 35 / 7 / 5 / 3 |
| `expected_route` (gold) | 27 accept / 23 review | 23 accept / 27 review |

La salud del live es idéntica: 50/50 válidas y 0 errores en ambos lotes.
Las dimensiones individuales mejoraron o quedaron parejas (intent
0.76→0.80, refund 0.92→1.00, actionability exacto 0.42→0.52, urgency
0.70→0.72); el problema es la **composición de ruta**: v6 emitió
41 review / 9 accept (v5: 25/25).

### 2. Ablation sobre los judgments congelados

Apagar **un veto a la vez** y recomponer la ruta con la misma
`route_tickets`; no se aplicó nada al lote medido:

| Variante | F1 | Δ vs base |
|---|---:|---:|
| Base v6 | 0.6324 | — |
| Sin `is_ambiguous` (corte 0.70) | 0.7756 | +0.1432 |
| Sin `confidence_bajo` (0.60) | 0.6703 | +0.0380 |
| Sin `is_contradictory` (0.50) | 0.6324 | 0.0000 |
| Sin confidence destino sensible (0.85) | 0.6324 | 0.0000 |
| Sin `needs_specialist` (0.50) | 0.6156 | −0.0168 |
| Sin veto de urgency modal (nivel≥2) | 0.6007 | −0.0317 |
| Sin security (0.65) | 0.6324 | 0.0000 |
| Sin refund (0.50) | 0.6324 | 0.0000 |
| Sin los 5 vetos nuevos de v6 a la vez | 0.5659 | −0.0664 |

Lectura: los vetos nuevos **en conjunto suman** (quitarlos todos hunde a
0.57); el problema es **uno**: `is_ambiguous ≥ 0.70` dispara en 9 de los 15
`accept→review` (valores 0.73–0.94).

### 3. Las tres señales humanas vs `expected_human` (agregados)

| Señal | Accuracy | Falsos positivos | Falsos negativos |
|---|---:|---:|---:|
| `is_ambiguous` | 0.70 | **13** | 2 |
| `is_contradictory` | 0.76 | 0 | 12 (casi no dispara) |
| `needs_specialist` | 0.86 | **0** | 7 (la más limpia) |

En filas gold no-humana `is_ambiguous` llega a 0.94 (p90 = 0.85). El OR
compuesto compra recall a costa de los 13 FP de la señal ambigua.

### 4. Asimetría estructural gold/pred

- El lote v6 no trajo columna `expected_ambiguous`, así que el gold
  materializa `is_ambiguous = 0.0` (fallback documentado): ese veto solo
  puede activarse del lado pred. Cuando Jev sobre-detecta ambigüedad es
  **100% FP de ruta**; el gold-ruta nunca lo contrarresta.
- Desalineación de rúbrica: a Jev se le preguntó "¿el texto es ambiguo?"
  (rúbrica amplia, corte 0.70 elegido en frío) y el curador etiquetó
  "¿requiere humano?" (rúbrica más estrecha). No son la misma dimensión.

### 5. Sweep del corte (solo diagnóstico)

Es **retuning post-hoc** y, por protocolo, **NO se aplica al lote v6**:

| Corte `is_ambiguous` | 0.70 (actual) | 0.75 | 0.80 | 0.85 | 0.90 | 0.95 |
|---|---:|---:|---:|---:|---:|---:|
| F1 | 0.6324 | 0.6608 | 0.6881 | 0.7640 | 0.7688 | 0.7947 |

Con 0.85+ el F1 superaría al de v5, pero subirlo sobre este lote sería el
truco v3.1 con otro nombre.

### 6. Implicaciones para v7 (cierre honesto)

- Candidato de corte: **0.85** (menor intervención que recupera el nivel de
  v5; **no es un resultado**, es una hipótesis seleccionada post-hoc sobre
  v6).
- Añadir columnas `expected_ambiguous` / `expected_contradictory` al lote
  curado para volver simétrico el veto y permitir auditoría por señal.
- Validación **obligatoria** en lote nuevo `tickets_v7_50.csv` con un solo
  live y sin retuning posterior. Ni el sweep ni la ablation son métricas
  oficiales.

v7 ya corrió (2026-09-24): route F1 **0.82**. El diagnóstico de arriba no se
recalcula ni se usa para otro corte.

## Reproducir

El live v7 ya corrió (un solo live, 2026-09-24). Repetirlo exige archivar el
protocolo v7 en `archive/` con su evidence y curar otro lote nuevo:
`freeze_evaluation.py` se niega a reescribir un manifest existente
(anti truco v3.1) y `verify_manifest` solo acepta el protocolo vigente.

```bash
.venv/Scripts/python.exe scripts/freeze_evaluation.py

.venv/Scripts/python.exe scripts/run_live_eval.py tickets \
  --env-file 'C:/ruta/local/.env' --allow-remote \
  --output evaluations/tickets_live_50.json

.venv/Scripts/python.exe scripts/run_live_eval.py retail \
  --output evaluations/retail_live_20.json
```
