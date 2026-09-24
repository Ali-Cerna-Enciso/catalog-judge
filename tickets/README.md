# Tickets: corpus público curado

`data/tickets_100.csv` contiene 100 filas sustantivamente distintas, derivadas de
100 filas English del corpus público Tobi-Bueck/customer-support-tickets. El
texto se tradujo/adaptó al español y se rubricó manualmente; no se conserva
`subject`/`body` original ni la columna `answer`.

El dataset declara que el corpus es generado y no contiene PII. El fixture
El protocolo v4 evalúa live el split `dev` como confirmation. El `holdout`
de v1–v3.1 está archivado y no se usa para tunear.

## Proveniencia y licencia

- Fuente: <https://huggingface.co/datasets/Tobi-Bueck/customer-support-tickets>
- Licencia de datos: CC BY-NC 4.0.
- La licencia MIT del código no sustituye la licencia de los datos.
- Curation map: [`data/curation_100.json`](data/curation_100.json).
- Rúbrica visible: [`RUBRIC.md`](RUBRIC.md).
- La selección usa queues variados y elimina placeholders, identificadores y
  texto original antes de guardar la traducción.

## Contrato Jev

Cada fila hace una llamada con diez preguntas atómicas (protocolo v7;
v5 usó ocho, con `requires_human` único):

`area`, `intent`, `urgency`, `is_ambiguous`, `is_contradictory`,
`needs_specialist`, `security_legal_risk`, `refund_or_replacement`,
`actionability`, `technical_repro`.

Los textos están en español; las instrucciones y rúbricas de Jev están en
inglés, como recomienda la documentación de TypeSafe. El código decide
destino, prioridad y ruta; Jev no elige una acción `auto/review/human`.

La evaluación live congelada usa las 50 filas `holdout`. El mock es heurístico,
no lee `expected_*` y no es evidencia de Jev. El export de evidence no incluye
texto de entrada.

Ver [`../DATA_SOURCES.md`](../DATA_SOURCES.md) y
[`../SECURITY.md`](../SECURITY.md).
