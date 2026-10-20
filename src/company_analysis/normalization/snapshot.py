"""Point-in-time snapshot of each company: the normalised inputs of every metric.

All fundamentals are measured at the same reference period (the latest one reported), so that
ratios never mix periods. Ratios use the reporting currency; the snapshot also carries the rates
needed to express absolute magnitudes in euros.
"""

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date

from company_analysis.config import NormalizationConfig
from company_analysis.figures import Figure, Status
from company_analysis.formatting import format_date
from company_analysis.models import (
    Bond,
    BondQuote,
    DataBundle,
    Equity,
    EquityPrice,
    FinancialFact,
    FinancialItem,
    Issuer,
    ItemKind,
    RatingAction,
)
from company_analysis.models.ratings import rating_notch
from company_analysis.normalization.fiscal import add_months, ltm_window_start
from company_analysis.normalization.fx import FxTable
from company_analysis.normalization.ltm import IssuerFacts, ReferencePeriod

FLOW_ITEMS = tuple(item for item in FinancialItem if item.kind is ItemKind.FLOW)
STOCK_ITEMS = tuple(item for item in FinancialItem if item.kind is ItemKind.STOCK)


@dataclass(frozen=True)
class BondSnapshot:
    bond: Bond
    rating: RatingAction | None  # current rating; the worst one if several agencies rate it
    spread: Figure  # basis points
    quote: BondQuote | None  # latest quote, even if it is too old to be used


@dataclass(frozen=True)
class CompanySnapshot:
    """Everything known about a company at ``as_of``, ready for the metrics."""

    issuer: Issuer
    as_of: date
    reference: ReferencePeriod | None
    flows: Mapping[FinancialItem, Figure]  # LTM at the reference period
    flows_prior_year: Mapping[FinancialItem, Figure]  # LTM one year earlier
    stocks: Mapping[FinancialItem, Figure]  # at the close of the reference period
    equity: Equity | None
    price: Figure  # listing currency
    price_date: date | None
    market_cap: Figure  # millions of the reporting currency
    eur_average_rate: Figure  # reporting currency per euro, average over the LTM window
    eur_closing_rate: Figure  # reporting currency per euro at the reference period close
    eur_spot_rate: Figure  # reporting currency per euro at the price date
    bonds: tuple[BondSnapshot, ...]

    @property
    def issuer_id(self) -> str:
        return self.issuer.issuer_id

    @property
    def currency(self) -> str:
        return self.issuer.reporting_currency

    def flow(self, item: FinancialItem) -> Figure:
        return self.flows[item]

    def flow_prior_year(self, item: FinancialItem) -> Figure:
        return self.flows_prior_year[item]

    def stock(self, item: FinancialItem) -> Figure:
        return self.stocks[item]


def _unavailable_items(
    items: tuple[FinancialItem, ...], suffix: str, status: Status, detail: str
) -> dict[FinancialItem, Figure]:
    return {item: Figure.unavailable(f"{item.label}{suffix}", status, detail) for item in items}


def _fundamentals(
    facts: IssuerFacts, as_of: date, config: NormalizationConfig
) -> tuple[
    ReferencePeriod | None,
    dict[FinancialItem, Figure],
    dict[FinancialItem, Figure],
    dict[FinancialItem, Figure],
]:
    reference = facts.reference_period()
    problem: tuple[Status, str] | None = None
    if reference is None:
        problem = (Status.MISSING, "no hay estados financieros publicados a la fecha de análisis")
    else:
        age = (as_of - reference.period_end).days
        if age > config.max_financials_age_days:
            problem = (
                Status.STALE,
                f"los últimos estados financieros son del {reference.label} ({age} días antes "
                f"de la fecha de análisis; máximo {config.max_financials_age_days})",
            )
    if problem is not None or reference is None:
        status, detail = problem or (Status.MISSING, "")
        return (
            reference,
            _unavailable_items(FLOW_ITEMS, " LTM", status, detail),
            _unavailable_items(FLOW_ITEMS, " LTM del año anterior", status, detail),
            _unavailable_items(STOCK_ITEMS, "", status, detail),
        )
    period, end = reference.fiscal_period, reference.period_end
    prior_end = add_months(end, -12)
    flows = {item: facts.ltm(item, period, end) for item in FLOW_ITEMS}
    prior = {
        item: facts.ltm(item, period, prior_end, label=f"{item.label} LTM del año anterior")
        for item in FLOW_ITEMS
    }
    stocks = {item: facts.balance(item, period, end) for item in STOCK_ITEMS}
    return reference, flows, prior, stocks


def _price(
    equity: Equity | None, prices: list[EquityPrice], as_of: date, config: NormalizationConfig
) -> tuple[Figure, date | None]:
    label = "Cotización"
    if equity is None:
        return Figure.unavailable(label, Status.MISSING, "el emisor no tiene acción cotizada"), None
    if not prices:
        return (
            Figure.unavailable(
                label, Status.MISSING, "sin cotizaciones hasta la fecha de análisis"
            ),
            None,
        )
    last = prices[-1]
    age = (as_of - last.price_date).days
    if age > config.max_price_age_days:
        detail = (
            f"la última cotización es del {format_date(last.price_date)} ({age} días antes de la "
            f"fecha de análisis; máximo {config.max_price_age_days})"
        )
        return Figure.unavailable(label, Status.STALE, detail), last.price_date
    detail = f"{last.currency} del {format_date(last.price_date)}"
    return Figure(label, last.close, detail=detail), last.price_date


def _market_cap(
    issuer: Issuer,
    equity: Equity | None,
    price: Figure,
    price_date: date | None,
    shares: Figure,
    fx: FxTable,
) -> Figure:
    label = f"Capitalización ({issuer.reporting_currency})"
    for figure in (price, shares):
        if not figure.ok:
            return Figure.unavailable(label, figure.status, figure.explanation())
    assert equity is not None
    assert price_date is not None
    rate = fx.cross(equity.currency, issuer.reporting_currency, price_date)
    if not rate.ok:
        return Figure.unavailable(label, rate.status, rate.explanation())
    value = price.number() * shares.number() * rate.number()
    return Figure(label, value, detail=f"precio × acciones del {format_date(price_date)}")


def _bond(
    bond: Bond,
    quotes: list[BondQuote],
    ratings: list[RatingAction],
    as_of: date,
    config: NormalizationConfig,
) -> BondSnapshot:
    latest_by_agency: dict[str, RatingAction] = {}
    for action in sorted(ratings, key=lambda action: action.rating_date):
        latest_by_agency[action.agency] = action
    rating = max(
        latest_by_agency.values(), key=lambda action: rating_notch(action.rating), default=None
    )
    label = "Diferencial (pb)"
    if not quotes:
        return BondSnapshot(
            bond, rating, Figure.unavailable(label, Status.MISSING, "el bono no cotiza"), None
        )
    last = quotes[-1]
    age = (as_of - last.quote_date).days
    if age > config.max_quote_age_days:
        detail = (
            f"la última cotización es del {format_date(last.quote_date)} ({age} días; "
            f"máximo {config.max_quote_age_days})"
        )
        spread = Figure.unavailable(label, Status.STALE, detail)
    else:
        detail = f"{last.spread_type.value} del {format_date(last.quote_date)}"
        spread = Figure(label, last.spread_bp, detail=detail)
    return BondSnapshot(bond, rating, spread, last)


@dataclass(frozen=True)
class _VisibleData:
    """The bundle's records visible at the analysis date, grouped for lookup."""

    facts: Mapping[str, list[FinancialFact]]  # by issuer
    equities: Mapping[str, Equity]  # by issuer
    prices: Mapping[str, list[EquityPrice]]  # by ISIN, oldest first
    bonds: Mapping[str, list[Bond]]  # outstanding bonds, by issuer
    quotes: Mapping[str, list[BondQuote]]  # by ISIN, oldest first
    ratings: Mapping[str, list[RatingAction]]  # by ISIN


def _group[T](
    records: Iterable[T], key: Callable[[T], str], visible: Callable[[T], bool]
) -> dict[str, list[T]]:
    groups: dict[str, list[T]] = defaultdict(list)
    for record in records:
        if visible(record):
            groups[key(record)].append(record)
    return groups


def _visible_data(bundle: DataBundle, as_of: date) -> _VisibleData:
    return _VisibleData(
        facts=_group(
            bundle.financial_facts, lambda f: f.issuer_id, lambda f: f.published_at <= as_of
        ),
        equities={equity.issuer_id: equity for equity in bundle.equities},
        prices=_group(
            sorted(bundle.equity_prices, key=lambda p: p.price_date),
            lambda p: p.isin,
            lambda p: p.price_date <= as_of,
        ),
        bonds=_group(
            sorted(bundle.bonds, key=lambda b: b.isin),
            lambda b: b.issuer_id,
            lambda b: b.issue_date <= as_of < b.maturity_date,
        ),
        quotes=_group(
            sorted(bundle.bond_quotes, key=lambda q: q.quote_date),
            lambda q: q.isin,
            lambda q: q.quote_date <= as_of,
        ),
        ratings=_group(bundle.ratings, lambda r: r.isin, lambda r: r.rating_date <= as_of),
    )


def _eur_rates(
    currency: str, reference: ReferencePeriod | None, fx: FxTable
) -> tuple[Figure, Figure]:
    """Average rate over the LTM window and closing rate at the reference period end."""
    if reference is None:
        detail = "no hay periodo de referencia"
        return (
            Figure.unavailable("Tipo de cambio medio", Status.MISSING, detail),
            Figure.unavailable("Tipo de cambio de cierre", Status.MISSING, detail),
        )
    end = reference.period_end
    return fx.average(currency, ltm_window_start(end), end), fx.rate(currency, end)


def _company_snapshot(
    issuer: Issuer, data: _VisibleData, fx: FxTable, as_of: date, config: NormalizationConfig
) -> CompanySnapshot:
    reference, flows, prior, stocks = _fundamentals(
        IssuerFacts(data.facts.get(issuer.issuer_id, [])), as_of, config
    )
    equity = data.equities.get(issuer.issuer_id)
    prices = data.prices.get(equity.isin, []) if equity is not None else []
    price, price_date = _price(equity, prices, as_of, config)
    shares = stocks[FinancialItem.SHARES_OUTSTANDING]
    average_rate, closing_rate = _eur_rates(issuer.reporting_currency, reference, fx)
    return CompanySnapshot(
        issuer=issuer,
        as_of=as_of,
        reference=reference,
        flows=flows,
        flows_prior_year=prior,
        stocks=stocks,
        equity=equity,
        price=price,
        price_date=price_date,
        market_cap=_market_cap(issuer, equity, price, price_date, shares, fx),
        eur_average_rate=average_rate,
        eur_closing_rate=closing_rate,
        eur_spot_rate=fx.rate(issuer.reporting_currency, price_date or as_of),
        bonds=tuple(
            _bond(
                bond,
                data.quotes.get(bond.isin, []),
                data.ratings.get(bond.isin, []),
                as_of,
                config,
            )
            for bond in data.bonds.get(issuer.issuer_id, [])
        ),
    )


def build_snapshots(
    bundle: DataBundle, as_of: date, config: NormalizationConfig
) -> list[CompanySnapshot]:
    """One snapshot per issuer, using only data available at ``as_of``."""
    fx = FxTable(
        (rate for rate in bundle.fx_rates if rate.rate_date <= as_of),
        max_age_days=config.max_fx_age_days,
    )
    data = _visible_data(bundle, as_of)
    return [
        _company_snapshot(issuer, data, fx, as_of, config)
        for issuer in sorted(bundle.issuers, key=lambda issuer: issuer.issuer_id)
    ]
