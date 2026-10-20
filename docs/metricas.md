# Diccionario de métricas

> Generado automáticamente a partir del registro de métricas (`src/company_analysis/metrics/`). No lo edites a mano: ejecuta `uv run python scripts/generate_metrics_doc.py`. Un test comprueba que está al día.

## Convenciones

- **Periodo de referencia.** Es el último periodo publicado a la fecha de análisis. Todas las magnitudes de una empresa se miden en él, para no mezclar periodos.
- **LTM (últimos doce meses).** Con datos anuales es el último ejercicio. Con un periodo intermedio: último ejercicio + acumulado del año en curso − mismo acumulado del año anterior.
- **Balance.** Saldo al cierre del periodo de referencia.
- **Divisas.** Las ratios se calculan en la divisa de reporte. La capitalización se pasa a esa divisa al tipo de cambio de la fecha de la cotización. Las magnitudes en euros usan el tipo medio de los doce meses para los flujos, el tipo de cierre para el balance y el tipo de la fecha de la cotización para los valores de mercado.
- **Ejercicios que no cierran en diciembre.** Se comparan con el año natural en el que cae la mayoría de sus meses (un ejercicio cerrado en marzo de 2026 se compara con 2025).
- **Antigüedad máxima.** Cotización de acciones 10 días, cotización de bonos 10 días, tipo de cambio 7 días y estados financieros 480 días.
- **Parámetros.** Tipo impositivo teórico del ROIC: 25 %. Tramos de rating: AAA-AA, A, BBB, BB, B, CCC o inferior. Mínimo de bonos por tramo: 3.
- **Unidades.** Importes en millones; los porcentajes se guardan como fracción (0,052 = 5,2 %).

Los valores por defecto de la antigüedad máxima y de los parámetros se pueden cambiar en `config/analysis.yaml`; cada ejecución guarda la configuración que usó.

## Estados de un dato

Un dato que falta o no aplica nunca se inventa: se marca con uno de estos estados y un detalle que explica el motivo.

| Estado | Significado |
|---|---|
| Con dato | El valor se ha calculado; se guardan los datos de entrada utilizados. |
| Sin dato | Falta algún dato de entrada; el detalle indica cuál. |
| No aplica | La métrica no tiene sentido para esa empresa (por ejemplo, EBITDA en un banco) o la empresa no tiene el instrumento (bonos). |
| División por cero | El denominador es cero. |
| No significativo | El cálculo es posible pero no tiene sentido económico (por ejemplo, un PER con pérdidas). |
| Dato desactualizado | Algún dato de entrada es más antiguo de lo permitido en la fecha de análisis. |
| Sin comparables suficientes | No hay suficientes comparables (empresas o bonos). |

## Renta variable

### PER (`pe_ratio`)

Veces que la capitalización bursátil contiene el beneficio neto atribuible de los últimos doce meses.

| | |
|---|---|
| Fórmula | Capitalización bursátil / Beneficio neto atribuible LTM |
| Unidad | x |
| Mejor si es | Más bajo |
| Aplica a | Todas las empresas |

**Interpretación.** Cuanto más bajo, más barata la acción en relación con sus beneficios. Conviene compararlo dentro del sector: el crecimiento y el riesgo justifican múltiplos distintos.

**Casos límite.**

- Beneficio negativo: no significativo (no existe múltiplo de unas pérdidas).
- Beneficio cero: división por cero.
- Cotización ausente o con más antigüedad de la permitida: sin dato o dato desactualizado.

### EV/EBITDA (`ev_to_ebitda`)

Valor de empresa (capitalización más deuda neta) en relación con el EBITDA de los últimos doce meses.

| | |
|---|---|
| Fórmula | (Capitalización bursátil + Deuda financiera − Caja) / EBITDA LTM |
| Unidad | x |
| Mejor si es | Más bajo |
| Aplica a | Todas salvo bancos, seguros |

**Interpretación.** Cuanto más bajo, más barata la empresa en relación con su generación operativa, con independencia de cómo se financia. Simplificación: el valor de empresa no incluye intereses minoritarios ni otros ajustes.

**Casos límite.**

- EBITDA negativo: no significativo.
- EBITDA cero: división por cero.
- Valor de empresa negativo o nulo (la caja neta supera la capitalización): no significativo.
- Bancos y aseguradoras: no aplica.

**Por qué no aplica.** No aplica a bancos y aseguradoras: su EBITDA, su deuda y su valor de empresa no son comparables con los de una empresa no financiera.

### FCF yield (`fcf_yield`)

Flujo de caja libre de los últimos doce meses en relación con la capitalización bursátil.

| | |
|---|---|
| Fórmula | (Flujo de caja operativo LTM − Capex LTM) / Capitalización bursátil |
| Unidad | % |
| Mejor si es | Más alto |
| Aplica a | Todas salvo bancos, seguros |

**Interpretación.** Cuanto más alto, más caja genera la empresa por cada euro de capitalización. Un valor negativo indica que consume caja.

**Casos límite.**

- Flujo de caja libre negativo: valor válido (negativo).
- Falta el flujo operativo o el capex: sin dato.
- Bancos y aseguradoras: no aplica (sus flujos operativos incluyen depósitos y préstamos).

**Por qué no aplica.** No aplica a bancos y aseguradoras: sus flujos de caja operativos incluyen los movimientos de depósitos, préstamos e inversiones de su actividad.

### ROE (`roe`)

Rentabilidad del beneficio neto atribuible sobre el patrimonio neto atribuible al cierre del periodo.

| | |
|---|---|
| Fórmula | Beneficio neto atribuible LTM / Patrimonio neto atribuible al cierre |
| Unidad | % |
| Mejor si es | Más alto |
| Aplica a | Todas las empresas |

**Interpretación.** Cuanto más alta, más rentable es el capital de los accionistas. Puede inflarse con mucho apalancamiento: conviene leerla junto con la deuda.

**Casos límite.**

- Patrimonio negativo: no significativo.
- Patrimonio cero: división por cero.
- Beneficio negativo: valor válido (negativo).
- Se usa el patrimonio al cierre y no la media del periodo (simplificación).

### ROIC (`roic`)

Rentabilidad operativa después de impuestos sobre el capital invertido (patrimonio más deuda neta).

| | |
|---|---|
| Fórmula | EBIT LTM × (1 − tipo impositivo teórico) / (Patrimonio neto total + Deuda financiera − Caja) |
| Unidad | % |
| Mejor si es | Más alto |
| Aplica a | Todas salvo bancos, seguros |

**Interpretación.** Cuanto más alta, más valor crea la empresa con el capital que emplea. El tipo impositivo teórico (25 % por defecto) se configura en config/analysis.yaml.

**Casos límite.**

- Capital invertido negativo (la caja neta supera el patrimonio): no significativo.
- Capital invertido cero: división por cero.
- EBIT negativo: valor válido (negativo).
- Bancos y aseguradoras: no aplica.

**Por qué no aplica.** No aplica a bancos y aseguradoras: su EBITDA, su deuda y su valor de empresa no son comparables con los de una empresa no financiera.

### Margen EBITDA (`ebitda_margin`)

Parte de las ventas que se convierte en EBITDA.

| | |
|---|---|
| Fórmula | EBITDA LTM / Ventas LTM |
| Unidad | % |
| Mejor si es | Más alto |
| Aplica a | Todas salvo bancos, seguros |

**Interpretación.** Cuanto más alto, más rentable es la operación. Los márgenes difieren mucho entre sectores.

**Casos límite.**

- EBITDA negativo: valor válido (margen negativo).
- Ventas cero: división por cero; ventas negativas: no significativo.
- Bancos y aseguradoras: no aplica.

**Por qué no aplica.** No aplica a bancos y aseguradoras: su EBITDA, su deuda y su valor de empresa no son comparables con los de una empresa no financiera.

### Crecimiento de ventas (`revenue_growth`)

Variación de las ventas de los últimos doce meses frente a los doce meses anteriores.

| | |
|---|---|
| Fórmula | Ventas LTM / Ventas LTM de un año antes − 1 |
| Unidad | % |
| Mejor si es | Más alto |
| Aplica a | Todas las empresas |

**Interpretación.** Cuanto más alto, más crece el negocio. Se calcula en la divisa de reporte para no mezclar el efecto de los tipos de cambio.

**Casos límite.**

- Faltan las ventas del año anterior: sin dato.
- Ventas del año anterior cero: división por cero; negativas: no significativo.

## Crédito

### Deuda neta/EBITDA (`net_debt_to_ebitda`)

Años de EBITDA necesarios para pagar la deuda neta.

| | |
|---|---|
| Fórmula | (Deuda financiera − Caja) / EBITDA LTM |
| Unidad | x |
| Mejor si es | Más bajo |
| Aplica a | Todas salvo bancos, seguros |

**Interpretación.** Cuanto más bajo, menor endeudamiento. Un valor negativo indica caja neta (más caja que deuda).

**Casos límite.**

- EBITDA negativo: no significativo (si además hay deuda neta positiva, salta la alerta de apalancamiento).
- EBITDA cero: división por cero.
- Caja neta: valor negativo válido.
- Bancos y aseguradoras: no aplica.

**Por qué no aplica.** No aplica a bancos y aseguradoras: su EBITDA, su deuda y su valor de empresa no son comparables con los de una empresa no financiera.

### Cobertura de intereses (`interest_coverage`)

Veces que el EBITDA cubre los gastos financieros.

| | |
|---|---|
| Fórmula | EBITDA LTM / Gastos financieros LTM |
| Unidad | x |
| Mejor si es | Más alto |
| Aplica a | Todas salvo bancos, seguros |

**Interpretación.** Cuanto más alta, más holgura para pagar los intereses.

**Casos límite.**

- Sin gastos financieros (por ejemplo, sin deuda): división por cero.
- EBITDA negativo: valor válido (cobertura negativa).
- Bancos y aseguradoras: no aplica.

**Por qué no aplica.** No aplica a bancos y aseguradoras: su EBITDA, su deuda y su valor de empresa no son comparables con los de una empresa no financiera.

### Deuda/capital (`debt_to_equity`)

Deuda financiera en relación con el patrimonio neto total.

| | |
|---|---|
| Fórmula | Deuda financiera / Patrimonio neto total |
| Unidad | x |
| Mejor si es | Más bajo |
| Aplica a | Todas salvo bancos, seguros |

**Interpretación.** Cuanto más baja, menos apalancada está la empresa en términos de balance.

**Casos límite.**

- Patrimonio negativo: no significativo.
- Patrimonio cero: división por cero.
- Sin deuda: valor cero, válido.
- Bancos y aseguradoras: no aplica (su deuda incluye la financiación de su actividad).

**Por qué no aplica.** No aplica a bancos y aseguradoras: su deuda incluye depósitos y la financiación de su actividad, y su solvencia se mide con ratios de capital.

### Diferencial frente a su tramo de rating (`spread_vs_rating_bucket`)

Diferencia entre el diferencial de cada bono y la mediana de los bonos de su mismo tramo de rating. Para la empresa, la mediana de sus bonos.

| | |
|---|---|
| Fórmula | Por bono: Diferencial del bono − Mediana del diferencial de los bonos del mismo tramo de rating y tipo de diferencial. Por empresa: mediana de sus bonos. |
| Unidad | pb |
| Mejor si es | Más alto |
| Aplica a | Todas las empresas |

**Interpretación.** Positivo: el bono paga más que sus comparables de rating (más compensación por el mismo rating). Negativo: paga menos. En la puntuación de crédito, más alto puntúa mejor; el deterioro se vigila con las alertas y los factores de apalancamiento.

**Casos límite.**

- Bono sin rating: sin dato.
- Tramo con menos bonos del mínimo (3 por defecto): sin comparables suficientes.
- Cotización con más antigüedad de la permitida: dato desactualizado.
- Empresa sin bonos vivos: no aplica.
- Bono con ratings de varias agencias: se usa el peor.

## Magnitudes en euros

### Capitalización bursátil (`market_cap_eur`)

Valor en bolsa de todas las acciones de la empresa.

| | |
|---|---|
| Fórmula | Cotización × Acciones en circulación, convertida a euros al tipo de cambio de la fecha de la cotización |
| Unidad | M EUR |
| Mejor si es | Informativa (sin sentido preferido) |
| Aplica a | Todas las empresas |

**Interpretación.** Tamaño de la empresa en bolsa; útil para filtrar el universo.

**Casos límite.**

- Falta el dato de origen o el tipo de cambio: sin dato.
- Los valores negativos (por ejemplo, EBITDA o deuda neta) son válidos.
- Cotización con más antigüedad de la permitida: dato desactualizado.

### Valor de empresa (EV) (`enterprise_value_eur`)

Capitalización más deuda neta: el valor del negocio para todos sus financiadores.

| | |
|---|---|
| Fórmula | (Capitalización + Deuda financiera − Caja) en la divisa de reporte, convertido a euros al tipo de cambio de la fecha de la cotización |
| Unidad | M EUR |
| Mejor si es | Informativa (sin sentido preferido) |
| Aplica a | Todas salvo bancos, seguros |

**Interpretación.** Base de los múltiplos de valoración de empresa (EV/EBITDA).

**Casos límite.**

- Falta el dato de origen o el tipo de cambio: sin dato.
- Los valores negativos (por ejemplo, EBITDA o deuda neta) son válidos.
- Bancos y aseguradoras: no aplica.

**Por qué no aplica.** No aplica a bancos y aseguradoras: su EBITDA, su deuda y su valor de empresa no son comparables con los de una empresa no financiera.

### Ventas LTM (`revenue_ltm_eur`)

Ventas de los últimos doce meses, en euros.

| | |
|---|---|
| Fórmula | Ventas LTM convertidas a euros al tipo de cambio medio de esos doce meses |
| Unidad | M EUR |
| Mejor si es | Informativa (sin sentido preferido) |
| Aplica a | Todas las empresas |

**Interpretación.** Tamaño del negocio, comparable entre empresas de distinta divisa.

**Casos límite.**

- Falta el dato de origen o el tipo de cambio: sin dato.
- Los valores negativos (por ejemplo, EBITDA o deuda neta) son válidos.

### EBITDA LTM (`ebitda_ltm_eur`)

EBITDA de los últimos doce meses, en euros.

| | |
|---|---|
| Fórmula | EBITDA LTM convertido a euros al tipo de cambio medio de esos doce meses |
| Unidad | M EUR |
| Mejor si es | Informativa (sin sentido preferido) |
| Aplica a | Todas salvo bancos, seguros |

**Interpretación.** Generación operativa del negocio, comparable entre divisas.

**Casos límite.**

- Falta el dato de origen o el tipo de cambio: sin dato.
- Los valores negativos (por ejemplo, EBITDA o deuda neta) son válidos.
- Bancos y aseguradoras: no aplica.

**Por qué no aplica.** No aplica a bancos y aseguradoras: su EBITDA, su deuda y su valor de empresa no son comparables con los de una empresa no financiera.

### Deuda neta (`net_debt_eur`)

Deuda financiera menos caja al cierre del periodo, en euros.

| | |
|---|---|
| Fórmula | (Deuda financiera − Caja) convertida a euros al tipo de cambio de la fecha de cierre del periodo |
| Unidad | M EUR |
| Mejor si es | Informativa (sin sentido preferido) |
| Aplica a | Todas salvo bancos, seguros |

**Interpretación.** Endeudamiento en términos absolutos; negativa si hay caja neta.

**Casos límite.**

- Falta el dato de origen o el tipo de cambio: sin dato.
- Los valores negativos (por ejemplo, EBITDA o deuda neta) son válidos.
- Bancos y aseguradoras: no aplica.

**Por qué no aplica.** No aplica a bancos y aseguradoras: su EBITDA, su deuda y su valor de empresa no son comparables con los de una empresa no financiera.
