# Diagnóstico post-hoc del protocolo v4 — dev (50 tickets, jev-1.13.0)

> **Qué es**: análisis de las evidencias ya publicadas
> (`evaluations/tickets_live_50.json`) para explicar el route macro-F1 0.55.
> Es *post-hoc*: usa el split `dev` ya gastado como confirmation.
> Los cortes "re-simulados" de la sección 8 son overfit de diagnóstico:
> sirven para elegir el diseño de v5 (lote nuevo), **no** para reportar una
> mejora de v4. Volver a correr un prompt tuneado sobre estas 50 filas = el
> truco de v3.1.
>
> Reproducir (sin key ni red; regenera este archivo):
> `.venv/Scripts/python.exe docs/protocol_v4_diagnostico/diagnostico.py`

## 0. Hallazgos

1. **El route F1 no lo rompen los 5 `accept→review` sino los 16**
   **`review→accept`**: precisión de `accept` 21/37 = 0.57.
2. **`expected_route` es casi una función de otras columnas del gold**:
   `human OR clarification OR urgency in (high,critical)` reproduce 49/50
   (`human=True` solo: 46/50, y 20/20 de `human=True` caen en `review`).
   El route mide la alineación entre la rúbrica de Jev y la de la
   curación, no la capacidad del modelo.
3. **`actionability` está colapsado**: 47/50 en el nivel 1; promedios
   1.13 / 1.13 / 1.23 por clase gold → el Score no separa ninguna clase
   (sección 6). El `focus` ancla al nivel 1 y los `examples` están en
   inglés sobre un corpus en español.
4. **Contradicciones instructions/criteria** (jaggedness 1.13 #7):
   `reclamo` acepta *seeks compensation* mientras `solicitud.not_for`
   dice que un pedido neutral de reembolso es `solicitud` (recall de
   `reclamo` 0.25, sección 12); `otro` prohíbe ser *fallback* mientras el
   gold usa `otro` para consultas genéricas (F1 0, sección 11).
5. **`requires_human` (0.64) tiene solape real de definición**: el gold no
   tiene rúbrica escrita; con corte 0.50 sube a 0.70 (sección 5).
6. **La confidence de Jev sí predice**: accuracy 0.89/0.95 en la banda
   [0.9,1] contra 0.40/0.60 en [0.5,0.75) (sección 4), y el piso actual
   de Choice (0.50) está bajo el piso documentado (0.60).
7. **`urgency`**: el gold nunca marca `critical` (support 0) pero el
   Score tiene nivel 3 → 2 errores gratuitos; `medium→low` 9/18
   (sección 7).

## 1. ¿De qué depende `expected_route` en el gold?

| Regla candidata sobre `expected_*` | Coincide con `expected_route` |
|---|---:|
| `human==True OR actionability==clarification` | 46/50 |
| `human==True` | 46/50 |
| `actionability==clarification` | 40/50 |
| `human OR actionability==clarification OR urgency in (high,critical)` | 49/50 |
| `human OR urgency in (high,critical)` | 49/50 |

**Por qué el gold marca `review` (n=24):**

- `human+action_clarif`: 12
- `human+urg_high`: 6
- `urg_high`: 4
- `human+action_clarif+sec`: 1
- `human+action_clarif+urg_high`: 1

## 2. Route: qué pasó fila por fila

| row | gold | pred | human noul | act score | urg score | conf area | conf intent | reasons |
|---|---|---|---:|---:|---:|---:|---:|---|
| hf-row-001753 | accept | review | 0.48 | 1.45 | 1.54 | 1.00 | 0.42 | intent.confidence_bajo=0.42; refund_or_replacement.noul=0.98; needs_clarificatio |
| hf-row-010635 | accept | accept | 0.11 | 1.75 | 0.00 | 1.00 | 1.00 | ruteo_por_umbral |
| hf-row-011564 | accept | accept | 0.47 | 1.02 | 0.00 | 0.90 | 1.00 | needs_clarification.score=1.02 |
| hf-row-015427 | review | accept | 0.18 | 1.65 | 0.00 | 0.88 | 1.00 | ruteo_por_umbral |
| hf-row-007059 | review | review | 0.28 | 1.44 | 2.04 | 0.45 | 1.00 | area.confidence_bajo=0.45; needs_clarification.score=1.44; urgency.score=2.04; t |
| hf-row-019949 | accept | accept | 0.56 | 1.02 | 0.73 | 1.00 | 1.00 | needs_clarification.score=1.02 |
| hf-row-018816 | accept | accept | 0.44 | 1.03 | 0.43 | 1.00 | 1.00 | refund_or_replacement.noul=0.99; needs_clarification.score=1.03 |
| hf-row-008151 | accept | accept | 0.22 | 1.19 | 0.45 | 1.00 | 0.93 | needs_clarification.score=1.19 |
| hf-row-009082 | review | review | 0.52 | 1.50 | 2.90 | 1.00 | 0.99 | urgency.score=2.9; technical_repro.noul=0.04 |
| hf-row-008694 | review | accept | 0.50 | 1.02 | 1.14 | 1.00 | 1.00 | needs_clarification.score=1.02 |
| hf-row-012247 | accept | accept | 0.34 | 1.05 | 0.01 | 0.93 | 1.00 | needs_clarification.score=1.05 |
| hf-row-008234 | accept | accept | 0.33 | 1.01 | 0.04 | 1.00 | 0.91 | needs_clarification.score=1.01 |
| hf-row-003225 | review | accept | 0.52 | 1.19 | 0.00 | 0.99 | 0.97 | needs_clarification.score=1.19 |
| hf-row-011332 | review | accept | 0.57 | 1.28 | 0.03 | 1.00 | 1.00 | needs_clarification.score=1.28 |
| hf-row-001666 | review | accept | 0.23 | 1.36 | 1.94 | 0.97 | 1.00 | needs_clarification.score=1.36 |
| hf-row-019360 | accept | accept | 0.34 | 1.21 | 0.04 | 1.00 | 1.00 | needs_clarification.score=1.21 |
| hf-row-001867 | review | accept | 0.75 | 1.34 | 1.07 | 0.99 | 0.52 | intent.confidence_media=0.52; requires_human.incertidumbre=0.75; refund_or_repla |
| hf-row-013639 | accept | accept | 0.23 | 1.25 | 0.00 | 1.00 | 1.00 | needs_clarification.score=1.25 |
| hf-row-007519 | accept | accept | 0.14 | 1.17 | 0.07 | 0.57 | 1.00 | area.confidence_media=0.57; needs_clarification.score=1.17 |
| hf-row-006566 | accept | review | 0.31 | 0.84 | 0.20 | 0.99 | 1.00 | actionability.score=0.84 |
| hf-row-009192 | review | accept | 0.47 | 1.21 | 1.07 | 1.00 | 0.97 | needs_clarification.score=1.21 |
| hf-row-010948 | review | accept | 0.76 | 1.05 | 0.55 | 0.94 | 0.53 | intent.confidence_media=0.53; requires_human.incertidumbre=0.76; needs_clarifica |
| hf-row-002092 | review | review | 0.85 | 0.86 | 0.00 | 0.78 | 0.38 | intent.confidence_bajo=0.38; requires_human.noul=0.85; actionability.score=0.86 |
| hf-row-002758 | review | review | 0.47 | 1.12 | 0.11 | 0.48 | 0.98 | area.confidence_bajo=0.48; needs_clarification.score=1.12 |
| hf-row-005075 | review | accept | 0.76 | 1.04 | 0.12 | 1.00 | 1.00 | requires_human.incertidumbre=0.76; needs_clarification.score=1.04 |
| hf-row-013455 | review | review | 0.75 | 0.98 | 0.38 | 0.73 | 1.00 | area.confidence_media=0.73; requires_human.incertidumbre=0.75; actionability.sco |
| hf-row-005687 | review | accept | 0.38 | 1.08 | 1.10 | 1.00 | 0.87 | refund_or_replacement.noul=0.53; needs_clarification.score=1.08 |
| hf-row-015088 | accept | review | 0.65 | 1.00 | 0.00 | 0.49 | 0.93 | area.confidence_bajo=0.49; requires_human.incertidumbre=0.65; needs_clarificatio |
| hf-row-019914 | review | review | 0.41 | 1.41 | 2.93 | 1.00 | 1.00 | needs_clarification.score=1.41; urgency.score=2.93; technical_repro.noul=0.04 |
| hf-row-012245 | review | accept | 0.21 | 1.23 | 1.56 | 1.00 | 1.00 | needs_clarification.score=1.23 |
| hf-row-008377 | accept | accept | 0.71 | 1.15 | 0.97 | 1.00 | 0.59 | intent.confidence_media=0.59; requires_human.incertidumbre=0.71; needs_clarifica |
| hf-row-001219 | accept | accept | 0.21 | 1.03 | 0.00 | 0.99 | 1.00 | needs_clarification.score=1.03 |
| hf-row-007288 | review | accept | 0.59 | 1.01 | 0.00 | 0.69 | 1.00 | area.confidence_media=0.69; needs_clarification.score=1.01 |
| hf-row-000568 | review | review | 0.87 | 1.03 | 0.08 | 0.55 | 0.96 | area.confidence_media=0.55; requires_human.noul=0.87; needs_clarification.score= |
| hf-row-017579 | accept | accept | 0.37 | 1.13 | 1.60 | 1.00 | 1.00 | needs_clarification.score=1.13 |
| hf-row-010959 | review | review | 0.45 | 1.03 | 0.02 | 0.47 | 1.00 | area.confidence_bajo=0.47; needs_clarification.score=1.03 |
| hf-row-003874 | accept | review | 0.43 | 1.04 | 0.05 | 0.46 | 1.00 | area.confidence_bajo=0.46; refund_or_replacement.noul=0.97; needs_clarification. |
| hf-row-001680 | accept | accept | 0.67 | 1.08 | 0.01 | 1.00 | 1.00 | requires_human.incertidumbre=0.67; needs_clarification.score=1.08 |
| hf-row-008967 | accept | accept | 0.41 | 1.03 | 1.42 | 1.00 | 1.00 | needs_clarification.score=1.03 |
| hf-row-016870 | accept | accept | 0.25 | 1.23 | 1.12 | 1.00 | 1.00 | needs_clarification.score=1.23 |
| hf-row-003651 | accept | accept | 0.55 | 1.12 | 1.03 | 0.99 | 1.00 | needs_clarification.score=1.12 |
| hf-row-018527 | review | accept | 0.84 | 1.00 | 0.11 | 0.94 | 0.99 | requires_human.incertidumbre=0.84; needs_clarification.score=1 |
| hf-row-001711 | accept | accept | 0.33 | 1.06 | 0.00 | 0.64 | 1.00 | area.confidence_media=0.64; needs_clarification.score=1.06 |
| hf-row-000220 | review | accept | 0.31 | 1.44 | 0.02 | 1.00 | 0.73 | intent.confidence_media=0.73; needs_clarification.score=1.44 |
| hf-row-014412 | accept | review | 0.29 | 0.92 | 1.21 | 1.00 | 0.68 | intent.confidence_media=0.68; actionability.score=0.92 |
| hf-row-006170 | accept | accept | 0.70 | 1.02 | 0.01 | 0.93 | 1.00 | requires_human.incertidumbre=0.7; needs_clarification.score=1.02 |
| hf-row-009719 | accept | accept | 0.28 | 1.10 | 1.10 | 0.96 | 0.99 | needs_clarification.score=1.1 |
| hf-row-012694 | accept | accept | 0.26 | 1.07 | 0.00 | 1.00 | 1.00 | needs_clarification.score=1.07 |
| hf-row-008358 | review | accept | 0.51 | 1.04 | 1.66 | 1.00 | 1.00 | needs_clarification.score=1.04 |
| hf-row-007049 | review | accept | 0.39 | 1.13 | 1.98 | 1.00 | 1.00 | needs_clarification.score=1.13 |

- gold=review → pred=accept (falsos accept): **16**
- gold=accept → pred=review (falsos review): **5**
- TP accept: 21 · TN review: 8

## 3. Las 16 filas `review` que el código aprobó

El route F1 no lo matan los 5 accept→review; lo matan los falsos accept.

| row | texto (preview) | gold reasons esperados | human | act | urg | conf a/i | predicho |
|---|---|---|---:|---:|---:|---|---|
| hf-row-015427 | Consulta sobre documentación de incorporación — ¿Qué documentación necesito para consultar | human+act_clarif | 0.18 | 1.65 | 0.00 | 0.88/1.00 | accept |
| hf-row-008694 | Integración devuelve un error — Una integración devuelve un error después de completar la  | urg_high | 0.50 | 1.02 | 1.14 | 1.00/1.00 | accept |
| hf-row-003225 | Solicitud de información sobre documentación — Pido orientación sobre qué documentación ex | human+act_clarif | 0.52 | 1.19 | 0.00 | 0.99/0.97 | accept |
| hf-row-011332 | Proceso de contratación — Tengo una consulta sobre el proceso de contratación y necesito c | human+act_clarif | 0.57 | 1.28 | 0.03 | 1.00/1.00 | accept |
| hf-row-001666 | Error reproducible al iniciar sesión — Al iniciar sesión aparece un error después de intro | urg_high | 0.23 | 1.36 | 1.94 | 0.97/1.00 | accept |
| hf-row-001867 | Producto llegó dañado — El producto llegó dañado y solicito una revisión antes de aceptar  | human+urg_high | 0.75 | 1.34 | 1.07 | 0.99/0.52 | accept |
| hf-row-009192 | Reembolso pendiente después de una devolución — La devolución fue aceptada, pero el estado | human+urg_high | 0.47 | 1.21 | 1.07 | 1.00/0.97 | accept |
| hf-row-010948 | La respuesta recibida no coincide — La respuesta no coincide con lo que solicité y necesit | human+act_clarif | 0.76 | 1.05 | 0.55 | 0.94/0.53 | accept |
| hf-row-005075 | Solicito restablecer un permiso — Pido revisar y restablecer un permiso de un entorno de d | human+act_clarif | 0.76 | 1.04 | 0.12 | 1.00/1.00 | accept |
| hf-row-005687 | Faltó un componente — El paquete no incluye un componente y solicito completar la entrega. | human+act_clarif | 0.38 | 1.08 | 1.10 | 1.00/0.87 | accept |
| hf-row-012245 | La aplicación se cierra inesperadamente — La aplicación se cierra inesperadamente al abrir | human+urg_high | 0.21 | 1.23 | 1.56 | 1.00/1.00 | accept |
| hf-row-007288 | Necesito orientación sobre una herramienta — Quisiera entender las opciones de una herrami | human+act_clarif | 0.59 | 1.01 | 0.00 | 0.69/1.00 | accept |
| hf-row-018527 | No encontré la información solicitada — La información disponible no aclara el siguiente p | human+act_clarif | 0.84 | 1.00 | 0.11 | 0.94/0.99 | accept |
| hf-row-000220 | Orientación para nuevo colaborador — Solicito orientación sobre el proceso de incorporació | human+act_clarif | 0.31 | 1.44 | 0.02 | 1.00/0.73 | accept |
| hf-row-008358 | Incidente de rendimiento — El rendimiento del sistema se deterioró y afecta el trabajo dia | human+urg_high | 0.51 | 1.04 | 1.66 | 1.00/1.00 | accept |
| hf-row-007049 | Sincronización detenida — La sincronización se detuvo y los cambios no llegan al destino e | urg_high | 0.39 | 1.13 | 1.98 | 1.00/1.00 | accept |

## 4. ¿Sirve la confidence de Jev? (accuracy por banda)

### area

| banda confidence | n | accuracy |
|---|---:|---:|
| [0.0, 0.5) | 5 | 1.00 |
| [0.5, 0.75) | 5 | 0.40 |
| [0.75, 0.9) | 2 | 0.50 |
| [0.9, 1.01) | 38 | 0.89 |

### intent

| banda confidence | n | accuracy |
|---|---:|---:|
| [0.0, 0.5) | 2 | 0.50 |
| [0.5, 0.75) | 5 | 0.60 |
| [0.75, 0.9) | 1 | 0.00 |
| [0.9, 1.01) | 42 | 0.95 |

## 5. `requires_human` (accuracy 0.64) — ¿dónde está el corte óptimo?

- **gold human=True** (n=20): 0.18, 0.21, 0.31, 0.38, 0.41, 0.45, 0.47, 0.47, 0.51, 0.52, 0.52, 0.57, 0.59, 0.75, 0.75, 0.76, 0.76, 0.84, 0.85, 0.87
- **gold human=False** (n=30): 0.11, 0.14, 0.21, 0.22, 0.23, 0.23, 0.25, 0.26, 0.28, 0.28, 0.29, 0.31, 0.33, 0.33, 0.34, 0.34, 0.37, 0.39, 0.41, 0.43, 0.44, 0.47, 0.48, 0.50, 0.55, 0.56, 0.65, 0.67, 0.70, 0.71

| corte noul | TP | FP | TN | FN | accuracy |
|---:|---:|---:|---:|---:|---:|
| 0.30 | 18 | 19 | 11 | 2 | 0.58 |
| 0.40 | 16 | 12 | 18 | 4 | 0.68 |
| 0.50 | 12 | 7 | 23 | 8 | 0.70 |
| 0.60 | 7 | 4 | 26 | 13 | 0.66 |
| 0.65 | 7 | 4 | 26 | 13 | 0.66 |
| 0.70 | 7 | 2 | 28 | 13 | 0.70 |
| 0.85 | 2 | 0 | 30 | 18 | 0.64 |

## 6. `actionability` — el Score se queda pegado en el nivel 1

| gold | n | score promedio | distribución (0/1/2/3) |
|---|---:|---:|---|
| clarification | 14 | 1.13 | 0/13/1/0 |
| standard_action | 28 | 1.13 | 0/27/1/0 |
| immediate_action | 8 | 1.23 | 0/7/1/0 |

## 7. `urgency` (accuracy 0.66) — score crudo por clase gold

| gold | n | score promedio | min | max |
|---|---:|---:|---:|---:|
| low | 20 | 0.10 | 0.00 | 1.03 |
| medium | 18 | 0.59 | 0.00 | 1.60 |
| high | 12 | 1.68 | 0.38 | 2.93 |

## 8. Re-simulación de route (overfit de diagnóstico, NO resultado)

| Variante | route macro-F1 | #accept | #review |
|---|---:|---:|---:|
| v4 actual | 0.550 | 37 | 13 |
| v4 + human>=0.50 → review | 0.660 | 23 | 27 |
| v4 + actionability<=1 → review | 0.576 | 36 | 14 |
| v4 + urgency>=2 → review (ya está) + human>=0.50 | 0.660 | 23 | 27 |
| v4 + conf(area/intent)<0.75 → review | 0.594 | 30 | 20 |
| v4 + actionability<=1 O human>=0.50 | 0.660 | 23 | 27 |
| solo expected_* (oracle señales del gold) | 0.919 | 30 | 20 |

## 9. Techo: si las predicciones de señales fueran perfectas

- route F1 con `expected_human`/`expected_actionability` perfectos: 0.919
- → el route F1 depende casi totalmente de `requires_human` (0.64) y `actionability` (0.28 exacto): **ahí está el trabajo de v5**.

## 10. Las 5 filas `accept` que el código vetó (falsos review)

| row | texto (preview) | reason del veto | area conf | intent conf | act |
|---|---|---|---:|---:|---:|
| hf-row-001753 | Cobro duplicado en una factura — La factura muestra dos cargos idénticos y solic | intent.confidence_bajo=0.42 | 1.00 | 0.42 | 1.45 |
| hf-row-006566 | Pasos para reproducir un fallo — Comparto los pasos que reproducen un fallo de l | actionability.score=0.84 | 0.99 | 1.00 | 0.84 |
| hf-row-015088 | Necesito comparar dos opciones — Quisiera comparar dos opciones antes de tomar u | area.confidence_bajo=0.49 | 0.49 | 0.93 | 1.00 |
| hf-row-003874 | Quiero cambiar un artículo — Solicito cambiar un artículo por otro del mismo tip | area.confidence_bajo=0.46 | 0.46 | 1.00 | 1.04 |
| hf-row-014412 | El sistema responde lentamente — Una función del sistema tarda demasiado y afect | intent.confidence_media=0.68; actionability.score=0.92 | 1.00 | 0.68 | 0.92 |

## 11. Área `otro` en el gold (F1 = 0) — textos y predicción

- `hf-row-011564` → predicho **atencion_cliente** (conf 0.90): Consulta sobre una opción de análisis — Necesito información sobre una opción de análisis sin s
- `hf-row-003225` → predicho **atencion_cliente** (conf 0.99): Solicitud de información sobre documentación — Pido orientación sobre qué documentación explica
- `hf-row-002092` → predicho **atencion_cliente** (conf 0.78): Pregunta sobre un proceso general — La descripción de un proceso general no indica con claridad
- `hf-row-007288` → predicho **atencion_cliente** (conf 0.69): Necesito orientación sobre una herramienta — Quisiera entender las opciones de una herramienta 

## 12. Intento `reclamo` en el gold (recall 0.25) — textos y predicción

- `hf-row-001753` → predicho **solicitud** (conf 0.42): Cobro duplicado en una factura — La factura muestra dos cargos idénticos y solicito la devoluci
- `hf-row-001867` → predicho **incidencia** (conf 0.52): Producto llegó dañado — El producto llegó dañado y solicito una revisión antes de aceptar el re
- `hf-row-010948` → predicho **reclamo** (conf 0.53): La respuesta recibida no coincide — La respuesta no coincide con lo que solicité y necesito una
- `hf-row-005687` → predicho **solicitud** (conf 0.87): Faltó un componente — El paquete no incluye un componente y solicito completar la entrega.

## 13. `requires_human`: dónde se cruzan las clases (con texto)

Gold=**True** con noul baja (Jev dice 'no hace humano'):

- noul 0.18 `hf-row-015427`: Consulta sobre documentación de incorporación — ¿Qué documentación necesito para cons
- noul 0.21 `hf-row-012245`: La aplicación se cierra inesperadamente — La aplicación se cierra inesperadamente al 
- noul 0.31 `hf-row-000220`: Orientación para nuevo colaborador — Solicito orientación sobre el proceso de incorpo
- noul 0.38 `hf-row-005687`: Faltó un componente — El paquete no incluye un componente y solicito completar la ent
- noul 0.41 `hf-row-019914`: Sistema no disponible para varios usuarios — Varias personas no pueden usar el sistem
- noul 0.45 `hf-row-010959`: Cómo configurar una opción — No está claro cómo configurar una opción del producto.
- noul 0.47 `hf-row-009192`: Reembolso pendiente después de una devolución — La devolución fue aceptada, pero el e
- noul 0.47 `hf-row-002758`: Solicitud de información sobre políticas — Pido información sobre una política de per

Gold=**False** con noul alta (Jev dice 'sí humano'):

- noul 0.71 `hf-row-008377`: La cantidad facturada no coincide — El importe de la factura no coincide con el detal
- noul 0.70 `hf-row-006170`: Solicito habilitar una función — Pido habilitar una función que está disponible en la
- noul 0.67 `hf-row-001680`: Solicito una propuesta comercial — Pido preparar una propuesta comercial con el alcan
- noul 0.65 `hf-row-015088`: Necesito comparar dos opciones — Quisiera comparar dos opciones antes de tomar una de
- noul 0.56 `hf-row-019949`: Una función no responde — Una función del producto no responde después de completar l
- noul 0.55 `hf-row-003651`: Necesito actualizar datos de facturación — Solicito corregir un dato administrativo d
- noul 0.50 `hf-row-008694`: Integración devuelve un error — Una integración devuelve un error después de completa
