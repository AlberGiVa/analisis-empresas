"""Builder of company snapshots with hand-picked inputs, for metric tests."""

from collections.abc import Mapping, Sequence
from datetime import date

from company_analysis.config import MetricsConfig
from company_analysis.figures import Figure, Status
from company_analysis.metrics import CompanyMetric, MetricResult, get_metric
from company_analysis.models import FinancialItem, Issuer
from company_analysis.normalization import BondSnapshot, CompanySnapshot
from company_analysis.normalization.snapshot import FLOW_ITEMS, STOCK_ITEMS
from tests import factories

NOT_PROVIDED = "no informado en el test"


def compute(
    metric_id: str, snapshot: CompanySnapshot, config: MetricsConfig | None = None
) -> MetricResult:
    """Compute one company-level metric directly from its registry definition."""
    definition = get_metric(metric_id)
    assert isinstance(definition, CompanyMetric)
    return definition.compute(snapshot, config or MetricsConfig())


def figure(label: str, value: float | Figure | None) -> Figure:
    """An available figure, the given figure, or a missing one when ``value`` is None."""
    if isinstance(value, Figure):
        return value
    if value is None:
        return Figure.unavailable(label, Status.MISSING, NOT_PROVIDED)
    return Figure(label, value)


def snapshot(
    *,
    issuer: Issuer | None = None,
    flows: Mapping[FinancialItem, float | Figure] | None = None,
    prior_flows: Mapping[FinancialItem, float | Figure] | None = None,
    stocks: Mapping[FinancialItem, float | Figure] | None = None,
    market_cap: float | Figure | None = None,
    eur_average_rate: float | Figure = 1.0,
    eur_closing_rate: float | Figure = 1.0,
    eur_spot_rate: float | Figure = 1.0,
    bonds: Sequence[BondSnapshot] = (),
    as_of: date = date(2025, 6, 30),
) -> CompanySnapshot:
    flows, prior_flows, stocks = flows or {}, prior_flows or {}, stocks or {}
    return CompanySnapshot(
        issuer=issuer or factories.issuer(),
        as_of=as_of,
        reference=None,
        flows={item: figure(f"{item.label} LTM", flows.get(item)) for item in FLOW_ITEMS},
        flows_prior_year={
            item: figure(f"{item.label} LTM del año anterior", prior_flows.get(item))
            for item in FLOW_ITEMS
        },
        stocks={item: figure(item.label, stocks.get(item)) for item in STOCK_ITEMS},
        equity=None,
        price=Figure.unavailable("Cotización", Status.MISSING, NOT_PROVIDED),
        price_date=None,
        market_cap=figure("Capitalización", market_cap),
        eur_average_rate=figure("Tipo de cambio medio", eur_average_rate),
        eur_closing_rate=figure("Tipo de cambio de cierre", eur_closing_rate),
        eur_spot_rate=figure("Tipo de cambio", eur_spot_rate),
        bonds=tuple(bonds),
    )
