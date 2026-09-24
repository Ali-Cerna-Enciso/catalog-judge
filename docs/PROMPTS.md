# Prompts y thresholds (protocolo v7)

Los prompts de **tickets** están en `src/catalog_judge/prompts.py` y los
cortes en `src/catalog_judge/routing.py`. Retail no usa prompts de Jev: la
política está en `src/catalog_judge/retail.py` y `retail/policy.json`.

## Contratos

- Retail: salidas de código `series_decision`, `handling_risk`,
  `exception_needed`, `route`.
- Tickets: `area`, `intent`, `urgency`, `is_ambiguous`,
  `is_contradictory`, `needs_specialist`, `security_legal_risk`,
  `refund_or_replacement`, `actionability`, `technical_repro`.

Cada ticket hace un único request (fan-out 10). Las features y la aritmética
retail se calculan en código.

Diseño de tickets:

- Instructions estructuradas (`question`/`focus`/`decide`).
- Choice con rúbrica de borde (`what`/`not_for`/`examples`); Score con
  niveles situacionales; Noul con borde explícito.
- No copiar umbrales de gold ni `expected_*` al prompt.
- Confirmation split congelado (`dev`); no se ajusta el prompt con esos
  resultados.

Novedades v7 (medido 2026-09-24: route F1 0.82, un solo live, sin retuning):

- Corte `is_ambiguous` 0.85 (candidato post-hoc del diagnóstico de v6:
  v6 midió 0.63 con 0.70; el 0.85 se congeló antes de este live y no se
  retuneó contra este lote).
- Lote con `expected_ambiguous` / `expected_contradictory` para gold simétrico.
- El resto del contrato se mantiene (10 preguntas, `modal_level`, KB,
  destinos sensibles, runner-up).

Contrato vigente (introducido en v6, en vigor desde entonces):

- `requires_human` fragmentado en 3 Noul atómicos con cortes propios
  (ambiguo 0.85 desde v7; contradicción 0.50, especialista 0.50);
  la ruta compone con OR y nombra la señal que dispara.
- `urgency` se lee por nivel modal (`modal_level` en `routing.py`):
  argmax de `probabilities`, con `round(score)` como fallback. Ruta,
  prioridad y evaluación comparten la función.
- El state incluye la KB `team_policy` (qué ejecuta el equipo sin pedir
  más datos); entra al `prompt_hash` y al `state_schema_sha256` del evidence.
- Destinos sensibles (`seguridad`, `pagos`) exigen `area.confidence ≥ 0.85`.
- `computed` guarda `area_runner_up` y `area_margin` (auditoría, sin veto).
- CatBoost documentado pero no implementado: requiere cientos de filas
  etiquetadas; ver `evaluations/README.md`.
- Fallback de gold: si el CSV no trae `expected_ambiguous` /
  `expected_contradictory`, esas señales caen a 0.0 (lotes anteriores a v7).

## Regla para cambios

1. Una dimensión por pregunta.
2. Set cerrado con `otro` cuando corresponda.
3. No cambiar el contrato sin actualizar tests, hashes y manifiesto.
4. No sumar `Noul` y `confidence`.
5. Congelar contrato/threshold antes de live.
6. Un error de contrato se corrige y se rerunea el confirmation completo.
