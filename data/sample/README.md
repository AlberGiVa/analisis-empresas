# Datos de ejemplo (sintéticos)

Datos **ficticios** generados por `scripts/generate_sample_data.py`. El generador es determinista:
la misma semilla produce exactamente los mismos ficheros, y un test lo comprueba. Son los únicos
datos que se versionan; los datos reales de mercado nunca se suben al repositorio.

Todos los identificadores son sintéticos: los ISIN empiezan por `ZZ` y los LEI por `ZZZZ` (códigos
no asignados), con dígitos de control válidos. Cualquier parecido de los nombres con empresas reales
es casual.

Para regenerarlos: `uv run python scripts/generate_sample_data.py`.

## Ficheros

| Fichero | Contenido | Unidades y convenciones |
|---|---|---|
| `issuers.csv` | 20 emisores: país, sector, industria, divisa de reporte, mes de cierre fiscal | |
| `equities.csv` | Una acción cotizada por emisor (mercado y divisa de cotización) | |
| `bonds.csv` | 40 bonos: divisa, cupón, emisión, vencimiento, prelación, nominal vivo | Cupón en %; nominal en millones |
| `financials.csv` | Estados financieros 2023-2025 en formato largo (una fila por emisor, periodo y partida) | Millones de la divisa de reporte; acciones en millones; gastos e inversiones en positivo |
| `equity_prices.csv` | Cierres semanales (viernes) del 06/01/2023 al 26/06/2026 | Divisa de cotización |
| `bond_quotes.csv` | Rentabilidad y diferencial semanales | Rentabilidad en %; diferencial (Z-spread) en pb |
| `ratings.csv` | Historial de rating de los bonos, de una agencia ficticia (`SAMPLE`) con escala S&P/Fitch | |
| `fx_rates.csv` | Tipos de cambio diarios (días hábiles) de USD, GBP, CHF y SEK | Unidades por 1 EUR (convención del BCE) |

Los resultados se publican (`published_at`) entre uno y tres meses después del cierre, para poder
reconstruir qué se sabía en cada fecha.

## Universo

| Sector | Empresas |
|---|---|
| Industria (6) | VALD, RHFD, CORV, SKRV, TALM, ASHC |
| Consumo (5) | MRND, LUMB, HOLL, PELL, VERD |
| Tecnología (4) | KELV, NEXL, ORBE, HELV |
| Utilities (2) | VTIB, GRSH |
| Financiero (3) | BVAL y WESB (bancos), AUBR (aseguradora) |

Los sectores tienen tamaños distintos a propósito. Con el mínimo de 5 comparables, Industria y
Consumo se comparan dentro de su sector (en los factores con dato suficiente) y el resto contra el
universo.

## Casos límite deliberados

| Caso | Empresa | Qué debe verse |
|---|---|---|
| EBITDA negativo | ORBE (2024 y 2025) | PER y EV/EBITDA "no significativos"; alerta de apalancamiento por EBITDA negativo con deuda neta positiva |
| Empresa sin deuda | HELV | Sin bonos; cobertura de intereses con "división por cero"; deuda neta negativa |
| Datos que faltan | CORV (capex de 2025), LUMB (gastos financieros de 2025), un bono de GRSH sin rating | FCF yield, cobertura y diferencial "sin dato" |
| Cotización desactualizada | SKRV (sin precios desde el 27/03/2026) | Métricas de mercado "dato desactualizado" a 30/06/2026 |
| Reporta en otra divisa | NEXL (cotiza en EUR, reporta en USD) | La capitalización se convierte a USD para calcular las ratios |
| Rebaja de rating entre periodos | ASHC (de BBB- a BB+ el 12/03/2026) | Alerta de rebaja; el bono pasa al tramo BB |
| Subida de rating | VERD (de A- a A el 20/05/2024) | No genera alerta |
| Ejercicio que no cierra en diciembre | PELL (cierra en marzo) | El ejercicio cerrado en marzo de 2026 se compara con el año 2025 |
| Tramo de rating con pocos bonos | GRSH (único bono AA-) | Diferencial "sin comparables suficientes" |
| Bancos y aseguradoras | BVAL, WESB, AUBR | Métricas basadas en EBITDA, deuda neta o EV con "no aplica" |

## Fechas de la demo

La demo ejecuta el análisis a 31/12/2025 y a 30/06/2026. Entre ambas fechas se publican los
resultados de 2025 y se produce la rebaja de rating de ASHC.
