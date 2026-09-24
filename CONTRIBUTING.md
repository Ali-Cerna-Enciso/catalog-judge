# Cómo contribuir

Antes de abrir un PR, revisa que el cambio mantenga las reglas del proyecto:

1. **Contrato de fan-out**: tickets envía sus diez preguntas en un solo
   request por fila; retail se resuelve en código, sin llamada a Jev.
2. **Cálculo en código**: los cálculos deterministas (umbrales, cortes,
   sanitización, agregación) viven en `src/`, no en prompts.
3. **Tests offline primero**: añade un test que cubra el cambio antes de
   tocar prompts, thresholds o sanitización.
4. **Suite local en verde**:
   `python -m pytest`, `ruff check .`, `mypy src` y
   `python -m compileall -q src app.py`.
5. **Datos**: sin datasets crudos, PII, keys ni logs con texto completo
   en el repo (ver `DATA_SOURCES.md` y `SECURITY.md`).
6. **Evidencia**: el holdout se congela antes de cualquier corrida live
   (`scripts/freeze_evaluation.py`) y cada corrida queda archivada en
   `evaluations/`. El mock es una heurística local para probar el flujo;
   la medición de Jev real sale solo de las corridas live con key.
