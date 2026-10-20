"""Absolute magnitudes in euros (the base currency), for information and screening filters."""

from company_analysis.config import MetricsConfig
from company_analysis.figures import Figure, Status
from company_analysis.metrics.base import (
    CompanyMetric,
    MetricCategory,
    MetricResult,
    Unit,
    first_unavailable,
    inputs_of,
)
from company_analysis.metrics.equity import FINANCIALS_EXCLUDED
from company_analysis.metrics.registry import register
from company_analysis.models import FINANCIAL_INSTITUTIONS
from company_analysis.models import FinancialItem as Item
from company_analysis.normalization import CompanySnapshot


def _to_euros(amount: float, rate: Figure, inputs: dict[str, float]) -> MetricResult:
    """Convert an amount in the reporting currency with a rate in units per euro."""
    if rate.number() <= 0:  # rates are validated as positive; kept as a safeguard
        return MetricResult.unavailable(Status.NOT_MEANINGFUL, "tipo de cambio no positivo", inputs)
    return MetricResult.computed(amount / rate.number(), inputs)


def _market_cap_eur(s: CompanySnapshot, _config: MetricsConfig) -> MetricResult:
    if problem := first_unavailable(s.market_cap, s.eur_spot_rate):
        return problem
    inputs = inputs_of(s.market_cap, s.eur_spot_rate)
    return _to_euros(s.market_cap.number(), s.eur_spot_rate, inputs)


def _enterprise_value_eur(s: CompanySnapshot, _config: MetricsConfig) -> MetricResult:
    debt, cash = s.stock(Item.TOTAL_DEBT), s.stock(Item.CASH)
    if problem := first_unavailable(s.market_cap, debt, cash, s.eur_spot_rate):
        return problem
    inputs = inputs_of(s.market_cap, debt, cash, s.eur_spot_rate)
    enterprise_value = s.market_cap.number() + debt.number() - cash.number()
    return _to_euros(enterprise_value, s.eur_spot_rate, inputs)


def _revenue_ltm_eur(s: CompanySnapshot, _config: MetricsConfig) -> MetricResult:
    revenue = s.flow(Item.REVENUE)
    if problem := first_unavailable(revenue, s.eur_average_rate):
        return problem
    return _to_euros(revenue.number(), s.eur_average_rate, inputs_of(revenue, s.eur_average_rate))


def _ebitda_ltm_eur(s: CompanySnapshot, _config: MetricsConfig) -> MetricResult:
    ebitda = s.flow(Item.EBITDA)
    if problem := first_unavailable(ebitda, s.eur_average_rate):
        return problem
    return _to_euros(ebitda.number(), s.eur_average_rate, inputs_of(ebitda, s.eur_average_rate))


def _net_debt_eur(s: CompanySnapshot, _config: MetricsConfig) -> MetricResult:
    debt, cash = s.stock(Item.TOTAL_DEBT), s.stock(Item.CASH)
    if problem := first_unavailable(debt, cash, s.eur_closing_rate):
        return problem
    inputs = inputs_of(debt, cash, s.eur_closing_rate)
    return _to_euros(debt.number() - cash.number(), s.eur_closing_rate, inputs)


_MAGNITUDE_EDGE_CASES = (
    "Falta el dato de origen o el tipo de cambio: sin dato.",
    "Los valores negativos (por ejemplo, EBITDA o deuda neta) son válidos.",
)

MARKET_CAP_EUR = register(
    CompanyMetric(
        metric_id="market_cap_eur",
        name="Capitalización bursátil",
        category=MetricCategory.MAGNITUDE,
        unit=Unit.MILLIONS_EUR,
        higher_is_better=None,
        description="Valor en bolsa de todas las acciones de la empresa.",
        formula=(
            "Cotización × Acciones en circulación, convertida a euros al tipo de cambio de la "
            "fecha de la cotización"
        ),
        interpretation="Tamaño de la empresa en bolsa; útil para filtrar el universo.",
        edge_cases=(
            *_MAGNITUDE_EDGE_CASES,
            "Cotización con más antigüedad de la permitida: dato desactualizado.",
        ),
        compute=_market_cap_eur,
    )
)

ENTERPRISE_VALUE_EUR = register(
    CompanyMetric(
        metric_id="enterprise_value_eur",
        name="Valor de empresa (EV)",
        category=MetricCategory.MAGNITUDE,
        unit=Unit.MILLIONS_EUR,
        higher_is_better=None,
        description=(
            "Capitalización más deuda neta: el valor del negocio para todos sus financiadores."
        ),
        formula=(
            "(Capitalización + Deuda financiera − Caja) en la divisa de reporte, convertido a "
            "euros al tipo de cambio de la fecha de la cotización"
        ),
        interpretation="Base de los múltiplos de valoración de empresa (EV/EBITDA).",
        edge_cases=(*_MAGNITUDE_EDGE_CASES, "Bancos y aseguradoras: no aplica."),
        excluded_industries=FINANCIAL_INSTITUTIONS,
        exclusion_reason=FINANCIALS_EXCLUDED,
        compute=_enterprise_value_eur,
    )
)

REVENUE_LTM_EUR = register(
    CompanyMetric(
        metric_id="revenue_ltm_eur",
        name="Ventas LTM",
        category=MetricCategory.MAGNITUDE,
        unit=Unit.MILLIONS_EUR,
        higher_is_better=None,
        description="Ventas de los últimos doce meses, en euros.",
        formula="Ventas LTM convertidas a euros al tipo de cambio medio de esos doce meses",
        interpretation="Tamaño del negocio, comparable entre empresas de distinta divisa.",
        edge_cases=_MAGNITUDE_EDGE_CASES,
        compute=_revenue_ltm_eur,
    )
)

EBITDA_LTM_EUR = register(
    CompanyMetric(
        metric_id="ebitda_ltm_eur",
        name="EBITDA LTM",
        category=MetricCategory.MAGNITUDE,
        unit=Unit.MILLIONS_EUR,
        higher_is_better=None,
        description="EBITDA de los últimos doce meses, en euros.",
        formula="EBITDA LTM convertido a euros al tipo de cambio medio de esos doce meses",
        interpretation="Generación operativa del negocio, comparable entre divisas.",
        edge_cases=(*_MAGNITUDE_EDGE_CASES, "Bancos y aseguradoras: no aplica."),
        excluded_industries=FINANCIAL_INSTITUTIONS,
        exclusion_reason=FINANCIALS_EXCLUDED,
        compute=_ebitda_ltm_eur,
    )
)

NET_DEBT_EUR = register(
    CompanyMetric(
        metric_id="net_debt_eur",
        name="Deuda neta",
        category=MetricCategory.MAGNITUDE,
        unit=Unit.MILLIONS_EUR,
        higher_is_better=None,
        description="Deuda financiera menos caja al cierre del periodo, en euros.",
        formula=(
            "(Deuda financiera − Caja) convertida a euros al tipo de cambio de la fecha de cierre "
            "del periodo"
        ),
        interpretation="Endeudamiento en términos absolutos; negativa si hay caja neta.",
        edge_cases=(*_MAGNITUDE_EDGE_CASES, "Bancos y aseguradoras: no aplica."),
        excluded_industries=FINANCIAL_INSTITUTIONS,
        exclusion_reason=FINANCIALS_EXCLUDED,
        compute=_net_debt_eur,
    )
)
