"""Equity metrics: the company seen by a shareholder (valuation, profitability, growth)."""

from company_analysis.config import MetricsConfig
from company_analysis.figures import Status
from company_analysis.formatting import format_number
from company_analysis.metrics.base import (
    CompanyMetric,
    MetricCategory,
    MetricResult,
    Unit,
    divide,
    first_unavailable,
    inputs_of,
)
from company_analysis.metrics.registry import register
from company_analysis.models import FINANCIAL_INSTITUTIONS
from company_analysis.models import FinancialItem as Item
from company_analysis.normalization import CompanySnapshot

FINANCIALS_EXCLUDED = (
    "No aplica a bancos y aseguradoras: su EBITDA, su deuda y su valor de empresa no son "
    "comparables con los de una empresa no financiera."
)


def _pe_ratio(s: CompanySnapshot, _config: MetricsConfig) -> MetricResult:
    market_cap, net_income = s.market_cap, s.flow(Item.NET_INCOME)
    if problem := first_unavailable(market_cap, net_income):
        return problem
    inputs = inputs_of(market_cap, net_income)
    return divide(market_cap.number(), net_income, inputs, unit=f"M {s.currency}")


def _ev_to_ebitda(s: CompanySnapshot, _config: MetricsConfig) -> MetricResult:
    market_cap, debt, cash = s.market_cap, s.stock(Item.TOTAL_DEBT), s.stock(Item.CASH)
    ebitda = s.flow(Item.EBITDA)
    if problem := first_unavailable(market_cap, debt, cash, ebitda):
        return problem
    inputs = inputs_of(market_cap, debt, cash, ebitda)
    enterprise_value = market_cap.number() + debt.number() - cash.number()
    if enterprise_value <= 0:
        return MetricResult.unavailable(
            Status.NOT_MEANINGFUL,
            f"el valor de empresa es negativo o nulo ({format_number(enterprise_value)} "
            f"M {s.currency}): la caja neta supera la capitalización",
            inputs,
        )
    return divide(enterprise_value, ebitda, inputs, unit=f"M {s.currency}")


def _fcf_yield(s: CompanySnapshot, _config: MetricsConfig) -> MetricResult:
    operating_cash_flow = s.flow(Item.OPERATING_CASH_FLOW)
    capex, market_cap = s.flow(Item.CAPITAL_EXPENDITURE), s.market_cap
    if problem := first_unavailable(operating_cash_flow, capex, market_cap):
        return problem
    inputs = inputs_of(operating_cash_flow, capex, market_cap)
    free_cash_flow = operating_cash_flow.number() - capex.number()
    return divide(free_cash_flow, market_cap, inputs, unit=f"M {s.currency}")


def _roe(s: CompanySnapshot, _config: MetricsConfig) -> MetricResult:
    net_income, equity = s.flow(Item.NET_INCOME), s.stock(Item.EQUITY_ATTRIBUTABLE)
    if problem := first_unavailable(net_income, equity):
        return problem
    return divide(
        net_income.number(), equity, inputs_of(net_income, equity), unit=f"M {s.currency}"
    )


def _roic(s: CompanySnapshot, config: MetricsConfig) -> MetricResult:
    ebit, equity = s.flow(Item.EBIT), s.stock(Item.TOTAL_EQUITY)
    debt, cash = s.stock(Item.TOTAL_DEBT), s.stock(Item.CASH)
    if problem := first_unavailable(ebit, equity, debt, cash):
        return problem
    inputs = inputs_of(ebit, equity, debt, cash) | {
        "Tipo impositivo teórico": config.notional_tax_rate
    }
    nopat = ebit.number() * (1 - config.notional_tax_rate)
    invested_capital = equity.number() + debt.number() - cash.number()
    if invested_capital == 0:
        return MetricResult.unavailable(
            Status.DIVISION_BY_ZERO, "el capital invertido es cero", inputs
        )
    if invested_capital < 0:
        return MetricResult.unavailable(
            Status.NOT_MEANINGFUL,
            f"el capital invertido es negativo ({format_number(invested_capital)} "
            f"M {s.currency}): la caja neta supera el patrimonio",
            inputs,
        )
    return MetricResult.computed(nopat / invested_capital, inputs)


def _ebitda_margin(s: CompanySnapshot, _config: MetricsConfig) -> MetricResult:
    ebitda, revenue = s.flow(Item.EBITDA), s.flow(Item.REVENUE)
    if problem := first_unavailable(ebitda, revenue):
        return problem
    return divide(ebitda.number(), revenue, inputs_of(ebitda, revenue), unit=f"M {s.currency}")


def _gross_margin(s: CompanySnapshot, _config: MetricsConfig) -> MetricResult:
    gross_profit, revenue = s.flow(Item.GROSS_PROFIT), s.flow(Item.REVENUE)
    if problem := first_unavailable(gross_profit, revenue):
        return problem
    return divide(
        gross_profit.number(), revenue, inputs_of(gross_profit, revenue), unit=f"M {s.currency}"
    )


def _fcf_conversion(s: CompanySnapshot, _config: MetricsConfig) -> MetricResult:
    operating_cash_flow = s.flow(Item.OPERATING_CASH_FLOW)
    capex, net_income = s.flow(Item.CAPITAL_EXPENDITURE), s.flow(Item.NET_INCOME)
    if problem := first_unavailable(operating_cash_flow, capex, net_income):
        return problem
    inputs = inputs_of(operating_cash_flow, capex, net_income)
    free_cash_flow = operating_cash_flow.number() - capex.number()
    return divide(free_cash_flow, net_income, inputs, unit=f"M {s.currency}")


def _revenue_growth(s: CompanySnapshot, _config: MetricsConfig) -> MetricResult:
    revenue, previous = s.flow(Item.REVENUE), s.flow_prior_year(Item.REVENUE)
    if problem := first_unavailable(revenue, previous):
        return problem
    inputs = inputs_of(revenue, previous)
    ratio = divide(revenue.number(), previous, inputs, unit=f"M {s.currency}")
    if ratio.value is None:
        return ratio
    return MetricResult.computed(ratio.value - 1, inputs)


PE_RATIO = register(
    CompanyMetric(
        metric_id="pe_ratio",
        name="PER",
        category=MetricCategory.EQUITY,
        unit=Unit.MULTIPLE,
        higher_is_better=False,
        description=(
            "Veces que la capitalización bursátil contiene el beneficio neto atribuible de los "
            "últimos doce meses."
        ),
        formula="Capitalización bursátil / Beneficio neto atribuible LTM",
        interpretation=(
            "Cuanto más bajo, más barata la acción en relación con sus beneficios. Conviene "
            "compararlo dentro del sector: el crecimiento y el riesgo justifican múltiplos "
            "distintos."
        ),
        edge_cases=(
            "Beneficio negativo: no significativo (no existe múltiplo de unas pérdidas).",
            "Beneficio cero: división por cero.",
            "Cotización ausente o con más antigüedad de la permitida: sin dato o dato "
            "desactualizado.",
        ),
        compute=_pe_ratio,
    )
)

EV_TO_EBITDA = register(
    CompanyMetric(
        metric_id="ev_to_ebitda",
        name="EV/EBITDA",
        category=MetricCategory.EQUITY,
        unit=Unit.MULTIPLE,
        higher_is_better=False,
        description=(
            "Valor de empresa (capitalización más deuda neta) en relación con el EBITDA de los "
            "últimos doce meses."
        ),
        formula="(Capitalización bursátil + Deuda financiera − Caja) / EBITDA LTM",
        interpretation=(
            "Cuanto más bajo, más barata la empresa en relación con su generación operativa, con "
            "independencia de cómo se financia. Simplificación: el valor de empresa no incluye "
            "intereses minoritarios ni otros ajustes."
        ),
        edge_cases=(
            "EBITDA negativo: no significativo.",
            "EBITDA cero: división por cero.",
            "Valor de empresa negativo o nulo (la caja neta supera la capitalización): no "
            "significativo.",
            "Bancos y aseguradoras: no aplica.",
        ),
        excluded_industries=FINANCIAL_INSTITUTIONS,
        exclusion_reason=FINANCIALS_EXCLUDED,
        compute=_ev_to_ebitda,
    )
)

FCF_YIELD = register(
    CompanyMetric(
        metric_id="fcf_yield",
        name="FCF yield",
        category=MetricCategory.EQUITY,
        unit=Unit.PERCENT,
        higher_is_better=True,
        description=(
            "Flujo de caja libre de los últimos doce meses en relación con la capitalización "
            "bursátil."
        ),
        formula="(Flujo de caja operativo LTM − Capex LTM) / Capitalización bursátil",
        interpretation=(
            "Cuanto más alto, más caja genera la empresa por cada euro de capitalización. Un "
            "valor negativo indica que consume caja."
        ),
        edge_cases=(
            "Flujo de caja libre negativo: valor válido (negativo).",
            "Falta el flujo operativo o el capex: sin dato.",
            "Bancos y aseguradoras: no aplica (sus flujos operativos incluyen depósitos y "
            "préstamos).",
        ),
        excluded_industries=FINANCIAL_INSTITUTIONS,
        exclusion_reason=(
            "No aplica a bancos y aseguradoras: sus flujos de caja operativos incluyen los "
            "movimientos de depósitos, préstamos e inversiones de su actividad."
        ),
        compute=_fcf_yield,
    )
)

ROE = register(
    CompanyMetric(
        metric_id="roe",
        name="ROE",
        category=MetricCategory.EQUITY,
        unit=Unit.PERCENT,
        higher_is_better=True,
        description=(
            "Rentabilidad del beneficio neto atribuible sobre el patrimonio neto atribuible al "
            "cierre del periodo."
        ),
        formula="Beneficio neto atribuible LTM / Patrimonio neto atribuible al cierre",
        interpretation=(
            "Cuanto más alta, más rentable es el capital de los accionistas. Puede inflarse con "
            "mucho apalancamiento: conviene leerla junto con la deuda."
        ),
        edge_cases=(
            "Patrimonio negativo: no significativo.",
            "Patrimonio cero: división por cero.",
            "Beneficio negativo: valor válido (negativo).",
            "Se usa el patrimonio al cierre y no la media del periodo (simplificación).",
        ),
        compute=_roe,
    )
)

ROIC = register(
    CompanyMetric(
        metric_id="roic",
        name="ROIC",
        category=MetricCategory.EQUITY,
        unit=Unit.PERCENT,
        higher_is_better=True,
        description=(
            "Rentabilidad operativa después de impuestos sobre el capital invertido (patrimonio "
            "más deuda neta)."
        ),
        formula=(
            "EBIT LTM × (1 − tipo impositivo teórico) / (Patrimonio neto total + Deuda "
            "financiera − Caja)"
        ),
        interpretation=(
            "Cuanto más alta, más valor crea la empresa con el capital que emplea. El tipo "
            "impositivo teórico (25 % por defecto) se configura en config/analysis.yaml."
        ),
        edge_cases=(
            "Capital invertido negativo (la caja neta supera el patrimonio): no significativo.",
            "Capital invertido cero: división por cero.",
            "EBIT negativo: valor válido (negativo).",
            "Bancos y aseguradoras: no aplica.",
        ),
        excluded_industries=FINANCIAL_INSTITUTIONS,
        exclusion_reason=FINANCIALS_EXCLUDED,
        compute=_roic,
    )
)

EBITDA_MARGIN = register(
    CompanyMetric(
        metric_id="ebitda_margin",
        name="Margen EBITDA",
        category=MetricCategory.EQUITY,
        unit=Unit.PERCENT,
        higher_is_better=True,
        description="Parte de las ventas que se convierte en EBITDA.",
        formula="EBITDA LTM / Ventas LTM",
        interpretation=(
            "Cuanto más alto, más rentable es la operación. Los márgenes difieren mucho entre "
            "sectores."
        ),
        edge_cases=(
            "EBITDA negativo: valor válido (margen negativo).",
            "Ventas cero: división por cero; ventas negativas: no significativo.",
            "Bancos y aseguradoras: no aplica.",
        ),
        excluded_industries=FINANCIAL_INSTITUTIONS,
        exclusion_reason=FINANCIALS_EXCLUDED,
        compute=_ebitda_margin,
    )
)

GROSS_MARGIN = register(
    CompanyMetric(
        metric_id="gross_margin",
        name="Margen bruto",
        category=MetricCategory.EQUITY,
        unit=Unit.PERCENT,
        higher_is_better=True,
        description=(
            "Parte de las ventas que queda después del coste directo de lo vendido. Mide el poder "
            "de fijación de precios y la calidad del negocio."
        ),
        formula="Beneficio bruto LTM / Ventas LTM",
        interpretation=(
            "Un margen bruto alto y estable suele indicar ventajas competitivas. Compárese dentro "
            "del mismo sector: los márgenes brutos de un fabricante y de un distribuidor no se "
            "parecen."
        ),
        edge_cases=(
            "La empresa no publica beneficio bruto: sin dato (no se reconstruye).",
            "Ventas cero: división por cero; ventas negativas: no significativo.",
            "Bancos y aseguradoras: no aplica.",
        ),
        excluded_industries=FINANCIAL_INSTITUTIONS,
        exclusion_reason=FINANCIALS_EXCLUDED,
        compute=_gross_margin,
    )
)

FCF_CONVERSION = register(
    CompanyMetric(
        metric_id="fcf_conversion",
        name="Conversión en caja",
        category=MetricCategory.EQUITY,
        unit=Unit.PERCENT,
        higher_is_better=True,
        description=(
            "Parte del beneficio neto que se convierte en flujo de caja libre. Distingue el "
            "beneficio que se cobra del que solo está en la contabilidad."
        ),
        formula="(Flujo de caja operativo LTM − Capex LTM) / Beneficio neto atribuible LTM",
        interpretation=(
            "Cerca o por encima del 100 %, el beneficio se traduce en caja. Muy por debajo, el "
            "negocio consume caja en inversiones o en circulante."
        ),
        edge_cases=(
            "Beneficio neto cero: división por cero; negativo: no significativo.",
            "Flujo de caja libre negativo con beneficio positivo: valor válido (negativo).",
            "Bancos y aseguradoras: no aplica.",
        ),
        excluded_industries=FINANCIAL_INSTITUTIONS,
        exclusion_reason=FINANCIALS_EXCLUDED,
        compute=_fcf_conversion,
    )
)

REVENUE_GROWTH = register(
    CompanyMetric(
        metric_id="revenue_growth",
        name="Crecimiento de ventas",
        category=MetricCategory.EQUITY,
        unit=Unit.PERCENT,
        higher_is_better=True,
        description=(
            "Variación de las ventas de los últimos doce meses frente a los doce meses anteriores."
        ),
        formula="Ventas LTM / Ventas LTM de un año antes − 1",
        interpretation=(
            "Cuanto más alto, más crece el negocio. Se calcula en la divisa de reporte para no "
            "mezclar el efecto de los tipos de cambio."
        ),
        edge_cases=(
            "Faltan las ventas del año anterior: sin dato.",
            "Ventas del año anterior cero: división por cero; negativas: no significativo.",
        ),
        compute=_revenue_growth,
    )
)
