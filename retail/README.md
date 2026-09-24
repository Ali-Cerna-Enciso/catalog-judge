# Retail: demanda pública y política de catálogo

`data/favorita_demand_96.csv` contiene 96 series públicas
`store_nbr × family` derivadas del mirror público del dataset Store Sales de
Corporación Favorita. El mirror no trae maestro de productos ni stock; por eso
no se inventan SKUs, nombres, stock, costo ni margen.

## Features calculadas por código

- `avg_sales`, `sales_cv`, `active_day_share`, `promo_share`
- `recent_vs_previous_ratio`
- `demand_drop_alert`: proxy de caída de demanda; no es quiebre de stock
- `replenishment_candidate`: proxy de aumento; no es inventario

## Política (no Jev)

`classify_retail_policy` aplica los umbrales de `policy.json` y produce
`series_decision`, `handling_risk`, `exception_needed` y `route`. El gold del
CSV sale de la misma función. Pedirle a Jev que re-derive esos umbrales a
partir de bandas nombradas era un mal uso: no hay juicio semántico, hay
aritmética.

`family` es contexto público para el tablero.

## Split

76 filas `dev` y 20 `holdout`. El holdout se usa como regresión de
política, no como eval de Jev.

## Licencia

Ver [`../DATA_SOURCES.md`](../DATA_SOURCES.md). Este repo no afirma relación
con Favorita.
