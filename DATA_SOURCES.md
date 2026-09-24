# Fuentes de datos

Los datasets se descargan sólo para preparación local. No se versionan raw
pesados ni se suben a servicios de terceros. La fecha de preparación de esta
revisión es 2026-09-23.

## Retail / Favorita

- Nombre público: **Store Sales - Time Series Forecasting** (Corporación
  Favorita), dataset original de Kaggle.
- Mirror público usado:
  <https://huggingface.co/datasets/t4tiana/store-sales-time-series-forecasting>
- Archivo: `train.csv` (121800373 bytes).
- SHA-256 raw:
  `99a1b7f4241821df10fa71f23abdd71c634f71f901e3cab1400c0f0c583f862c`.
- El mirror no declara una licencia independiente en su metadata; se cita el
  dataset original de Kaggle y no se redistribuye el raw.
- El mirror público disponible no contiene un maestro de productos ni stock.
  Para no inventar SKUs, el fixture usa 96 series explícitas
  `store_nbr × family`, equilibradas en ocho familias. No es un catálogo de
  productos con nombres; es una demo de demanda y features por serie.
- Derivado versionado: `retail/data/favorita_demand_96.csv`.
- SHA-256 derivado:
  `871b2d7d1c6ddf81dd458f5dcbbd7680a7ab3050fe916ced954eee07260f867f`.
- La muestra cubre `2017-06-21` a `2017-08-15`; la ventana reciente usa 28
  días calendario y la previa las 28 anteriores.
- El raw no contiene una columna de stock, costo o margen. El repo no los
  inventa. `demand_drop_alert` y `replenishment_candidate` son proxies de
  demanda; no son quiebre ni reposición de inventario.

## Tickets

- Dataset:
  <https://huggingface.co/datasets/Tobi-Bueck/customer-support-tickets>
- Archivo: `dataset-tickets-multi-lang-4-20k.csv`.
- Tamaño raw descargado: `18799808` bytes.
- SHA-256 raw:
  `9be3bf810584fe01e8e83383e83dfd33f4c3910938ecad03ef151da79d8f0635`.
- La metadata/README del dataset declara que el corpus es generado y no
  contiene PII. El fixture no lo llama tickets de clientes reales.
- Licencia de datos: **CC BY-NC 4.0**. La licencia MIT del código del repo no
  cambia esta licencia de datos.
- Selección: 100 filas English de queues variados, filtradas para no conservar
  placeholders, identificadores o texto original de terceros.
- Curación: `subject + body` se tradujo/adaptó al español y se asignó gold con
  una rúbrica visible en `tickets/data/curation_100.json`.
- Derivado versionado: `tickets/data/tickets_100.csv`.
- SHA-256 derivado:
  `324b20534ea6bb4fb59b1186bae063f5449c674905635f02156d888e3b157897`.
- SHA-256 de la mapa de curación:
  `9e8d34c03b8f6aa8073655f2087645638c4137e6c9decee7d7987d933b3f9855`.
- El fixture no contiene la columna `answer` ni el texto original.

## Tickets confirmation v5 / v6 / v7

Textos originales en español, rúbrica `ticket-rubric-v2`, no filas HF.
Licencia del código MIT; estos lotes no reutilizan el corpus CC BY-NC.

- `tickets/data/tickets_v5_50.csv`
- `tickets/data/tickets_v6_50.csv`
- `tickets/data/tickets_v7_50.csv` (SHA-256
  `d4b72c92db0540ae0a2044608822c2b39d0b7746783b6315187a45850ecaa41f`)

## Preparación reproducible

```bash
CATALOG_JUDGE_PUBLIC_TMP='C:/ruta/aprobada/catalog-judge-public' \
.venv/Scripts/python.exe scripts/prepare_public_fixtures.py \
  --raw-dir "$CATALOG_JUDGE_PUBLIC_TMP" --delete-raw
```

El script procesa Retail por chunks y, al terminar, permite borrar los raw. No
se ejecuta automáticamente en CI y no contiene credenciales.
