# 0004. Estados financieros en formato largo

- Fecha: 2026-10-20
- Estado: aceptada

## Contexto
Cada proveedor ofrece partidas distintas, y con el tiempo se necesitarán partidas nuevas para nuevas
métricas. Un esquema con una columna por partida obligaría a migrar la base cada vez.

## Decisión
- Una fila por emisor, periodo y partida: `(issuer_id, fiscal_period, period_end, item, value,
  currency, published_at)`.
- Las partidas válidas forman un catálogo cerrado (`FinancialItem`). Cada partida indica si es de
  flujo (cuenta de resultados, flujos de caja) o de saldo (balance) y su etiqueta en español.
- Convenciones:
  - importes en millones de la divisa de reporte, y acciones en millones;
  - gastos financieros y capex como importes positivos;
  - el beneficio neto y el patrimonio "atribuibles" son los de los accionistas de la dominante.
- Los periodos intermedios (Q1, H1, 9M) son acumulados desde el inicio del ejercicio.
- Las cifras de cada emisor deben venir en su divisa de reporte; la carga rechaza lo contrario.

## Consecuencias
- Añadir una partida es un cambio deliberado y revisado (ampliar el catálogo), sin migración.
- Las métricas leen partidas por su nombre en el catálogo, no por columnas.
