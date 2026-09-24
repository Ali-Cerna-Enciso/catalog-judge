# Contratos de datos

## Retail (política de código)

`retail/data/favorita_demand_96.csv` contiene features de demanda derivadas
por chunks del mirror público de Favorita. `series_id`, `store_nbr` y `family`
identifican una serie store×family; no se inventan nombres de producto, stock,
costo ni margen.

La decisión operativa (`series_decision`, `handling_risk`,
`exception_needed`, `route`) la calcula el código con
`classify_retail_policy` y los umbrales de `retail/policy.json`. Jev no
participa: no hay texto de SKU que juzgar, y el gold es una función de esos
umbrales.

`demand_bands` se conserva en `computed` como auditoría nombrada, no como
input de modelo.

`expected_*` es gold de la misma política y nunca se incluye en un state
remoto (retail no envía state remoto).

## Tickets

`tickets/data/tickets_100.csv` contiene 100 textos españoles curados a partir
de filas English del corpus público. `source_id` y `source_dataset` conservan
trazabilidad; no se guarda el texto original ni `answer`. La rúbrica del gold
está en `tickets/RUBRIC.md`.

El protocolo vigente (v7) evalúa live el split `confirmation` con un lote
nuevo por protocolo. Los lotes de v1 a v6 están archivados y no se re-miden.

## State y evidence

El state live de tickets no contiene `expected_*`. El evidence JSON incluye
hashes de dataset/contrato/thresholds, judgments, expected, ruta, latencia,
status y errores, pero no texto de entrada ni bodies remotos.

## Rutas

Retail: código. Tickets: diez preguntas Jev; los cortes de Choice, Score y
Noul son separados. El mock de tickets se marca `MOCK_EVALUATION_ONLY`.
