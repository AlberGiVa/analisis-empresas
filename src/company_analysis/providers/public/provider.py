"""Bundle of real data built from a downloaded snapshot, with a data-quality report.

Reading is deterministic: the same snapshot always gives the same bundle. Every decision that is
not a plain copy of a published figure (a fallback tag, a debt line not presented, a filing whose
figures are not yet in the structured data) is recorded so the analyst can review it.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from statistics import median
from typing import Any, ClassVar

from company_analysis.formatting import format_number
from company_analysis.models import (
    DataBundle,
    EquityPrice,
    FinancialFact,
    FinancialItem,
    FiscalPeriod,
    FxRate,
)
from company_analysis.providers.base import DataProvider
from company_analysis.providers.public.downloads import PRICES_FOLDER, read_manifest
from company_analysis.providers.public.market import (
    YAHOO_EXCHANGE_MIC,
    ecb_rates,
    nasdaq_prices,
    price_differences,
    yahoo_closes,
    yahoo_exchange,
)
from company_analysis.providers.public.sec import DebtComponent, Lineage, extract_financials
from company_analysis.providers.public.universe import CompanyEntry, Universe, load_universe

# A price that differs from the second source by more than this is reported.
PRICE_TOLERANCE = 0.005
PERIODIC_FORMS = {"10-K", "10-Q", "10-K/A", "10-Q/A"}


class SnapshotError(Exception):
    """The snapshot lacks a file the study needs."""


@dataclass(frozen=True)
class Filing:
    form: str
    period_end: date
    filed: date
    accession: str


@dataclass
class CompanyQuality:
    issuer_id: str
    name: str
    latest_filing: Filing | None
    latest_period_in_data: date | None
    lineage: list[Lineage]
    debt_breakdown: dict[date, list[DebtComponent]]
    prices: int
    last_price: EquityPrice | None
    compared_days: int
    max_price_difference: float | None
    max_difference_day: date | None
    warnings: list[str] = field(default_factory=list)
    distorted_ebitda: bool = False  # an unusual quarter falls inside the latest twelve months


@dataclass(frozen=True)
class FxCoverage:
    currency: str
    first: date
    last: date
    days: int


@dataclass
class PublicDataResult:
    bundle: DataBundle
    snapshot: Path
    created: str  # when the snapshot was downloaded (UTC, ISO)
    sources: list[tuple[str, str]]  # (source, url) of every file used
    companies: list[CompanyQuality]
    fx: list[FxCoverage]
    with_prices: bool = True  # False: only sources that may be republished (the public website)


def _json(folder: Path, relative: str) -> Any:
    path = folder / relative
    if not path.is_file():
        raise SnapshotError(f"Falta {relative} en la descarga {folder.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def latest_filing(submissions: Mapping[str, Any]) -> Filing | None:
    recent = submissions.get("filings", {}).get("recent", {})
    for index, form in enumerate(recent.get("form", [])):
        if form in PERIODIC_FORMS and recent["reportDate"][index]:
            return Filing(
                form=form,
                period_end=date.fromisoformat(recent["reportDate"][index]),
                filed=date.fromisoformat(recent["filingDate"][index]),
                accession=recent["accessionNumber"][index],
            )
    return None  # the list is newest first


def _company(
    folder: Path, company: CompanyEntry, *, with_prices: bool
) -> tuple[list[FinancialFact], list[EquityPrice], CompanyQuality]:
    companyfacts = _json(folder, f"sec/{company.id}.companyfacts.json")
    submissions = _json(folder, f"sec/{company.id}.submissions.json")
    extraction = extract_financials(
        company.id,
        companyfacts,
        currency=company.currency,
        fiscal_year_end_month=company.fiscal_year_end_month,
        debt_lines=company.debt_lines(),
        overrides=company.tags,
    )
    prices: list[EquityPrice] = []
    yahoo: Mapping[str, Any] = {}
    if with_prices:
        prices = nasdaq_prices(
            _json(folder, f"{PRICES_FOLDER}{company.id}.nasdaq.json"),
            isin=company.isin,
            currency=company.currency,
        )
        yahoo_path = folder / f"{PRICES_FOLDER}{company.id}.yahoo.json"
        if yahoo_path.is_file():
            yahoo = json.loads(yahoo_path.read_text(encoding="utf-8"))
    compared, worst, worst_day = price_differences(prices, yahoo_closes(yahoo))
    filing = latest_filing(submissions)
    periods = [entry.latest[1] for entry in extraction.lineage if entry.latest is not None]
    in_data = max(periods, default=None)
    quality = CompanyQuality(
        issuer_id=company.id,
        name=company.name,
        latest_filing=filing,
        latest_period_in_data=in_data,
        lineage=extraction.lineage,
        debt_breakdown=extraction.debt_breakdown,
        prices=len(prices),
        last_price=prices[-1] if prices else None,
        compared_days=compared,
        max_price_difference=worst,
        max_difference_day=worst_day,
    )
    _review(company, quality, yahoo, with_prices=with_prices)
    unusual = unusual_quarter_warnings(extraction.facts, company.currency)
    quality.warnings.extend(unusual)
    quality.distorted_ebitda = bool(unusual)
    return extraction.facts, prices, quality


def standalone_quarters(
    facts: Sequence[FinancialFact], item: FinancialItem
) -> list[tuple[date, float]]:
    """Each quarter on its own (Q1, H1 − Q1, 9M − H1, FY − 9M), from the latest publications.

    A quarter is left out when the cumulative period before it is missing.
    """
    latest: dict[tuple[FiscalPeriod, date], FinancialFact] = {}
    for fact in facts:
        if fact.item is item:
            key = (fact.fiscal_period, fact.period_end)
            if key not in latest or fact.published_at > latest[key].published_at:
                latest[key] = fact
    quarters: list[tuple[date, float]] = []
    previous: FinancialFact | None = None
    for (period, end), fact in sorted(
        latest.items(), key=lambda kv: (kv[0][1], kv[0][0] is FiscalPeriod.FY)
    ):
        if period is FiscalPeriod.Q1:
            quarters.append((end, fact.value))
        elif (
            previous is not None
            and _ORDER.index(period) == _ORDER.index(previous.fiscal_period) + 1
        ):
            quarters.append((end, fact.value - previous.value))
        previous = fact
    return quarters


_ORDER = [FiscalPeriod.Q1, FiscalPeriod.H1, FiscalPeriod.NINE_MONTHS, FiscalPeriod.FY]
UNUSUAL_LOW, UNUSUAL_HIGH = 0.5, 1.6  # share of the median quarter of the last two years


def unusual_quarter_warnings(facts: Sequence[FinancialFact], currency: str) -> list[str]:
    """Quarters whose operating income is far from the usual: probable non-recurring items.

    The study uses figures as published, so an impairment or the gain on a disposal goes straight
    into the twelve-month EBITDA. Nothing is corrected: it tells the analyst where to look.
    """
    quarters = standalone_quarters(facts, FinancialItem.EBIT)[-8:]
    if len(quarters) < 4:
        return []
    # The usual quarter ignores losses, so that a past impairment does not lower the reference.
    profits = [value for _, value in quarters if value > 0]
    if len(profits) < 3:
        return []
    usual = median(profits)
    # Only the four quarters of the latest twelve months move the metrics of the analysis.
    recent = quarters[-4:]
    return [
        f"Resultado operativo atípico en el trimestre cerrado el {end:%d/%m/%Y}, dentro de los "
        f"doce meses que usa el análisis: "
        f"{format_number(value, 0)} M {currency} frente a {format_number(usual, 0)} M de un "
        "trimestre típico de los dos últimos años. Probable partida no recurrente (un deterioro, "
        "la venta de un negocio…): el EBITDA contable de los doce meses que incluyen ese "
        "trimestre la recoge entera."
        for end, value in recent
        if value < UNUSUAL_LOW * usual or value > UNUSUAL_HIGH * usual
    ]


def _review(
    company: CompanyEntry,
    quality: CompanyQuality,
    yahoo: Mapping[str, Any],
    *,
    with_prices: bool,
) -> None:
    """Warnings the analyst should read before trusting the figures."""
    warnings = quality.warnings
    filing, in_data = quality.latest_filing, quality.latest_period_in_data
    if filing and in_data and filing.period_end > in_data:
        warnings.append(
            f"El último informe registrado ({filing.form} del periodo cerrado el "
            f"{filing.period_end:%d/%m/%Y}, presentado el {filing.filed:%d/%m/%Y}) todavía no "
            f"está en los datos estructurados de la SEC: se usan las cifras del "
            f"{in_data:%d/%m/%Y}."
        )
    for entry in quality.lineage:
        if entry.latest is None:
            warnings.append(f"{entry.item.label}: {entry.note}.")
        elif in_data and entry.latest[1] < in_data:
            warnings.append(
                f"{entry.item.label}: el último dato es del {entry.latest[1]:%d/%m/%Y}, anterior "
                f"al último periodo publicado ({in_data:%d/%m/%Y})."
            )
    for day, components in sorted(quality.debt_breakdown.items())[-1:]:
        missing = [c.line for c in components if c.tag is None]
        if missing:
            warnings.append(
                f"Deuda a {day:%d/%m/%Y}: {', '.join(missing)} no aparece en ese balance y cuenta "
                "como cero."
            )
    if not with_prices:
        return
    if quality.compared_days == 0:
        warnings.append("No se han podido contrastar las cotizaciones con una segunda fuente.")
    elif quality.max_price_difference and quality.max_price_difference > PRICE_TOLERANCE:
        warnings.append(
            f"Cotizaciones: diferencia máxima con Yahoo Finance del "
            f"{quality.max_price_difference:.2%} el {quality.max_difference_day:%d/%m/%Y}."
        )
    exchange = yahoo_exchange(yahoo)
    mic = YAHOO_EXCHANGE_MIC.get(exchange or "")
    if mic and mic != company.exchange:
        warnings.append(f"Mercado: el universo dice {company.exchange} y Yahoo, {mic}.")


def build(universe: Universe, folder: Path) -> PublicDataResult:
    manifest = read_manifest(folder)
    with_prices = manifest.get("cotizaciones", True) is not False  # older snapshots had prices
    facts: list[FinancialFact] = []
    prices: list[EquityPrice] = []
    companies: list[CompanyQuality] = []
    for company in universe.companies:
        company_facts, company_prices, quality = _company(folder, company, with_prices=with_prices)
        facts += company_facts
        prices += company_prices
        companies.append(quality)
    rates: list[FxRate] = []
    coverage: list[FxCoverage] = []
    for currency in universe.currencies:
        path = folder / f"bce/{currency}.csv"
        if not path.is_file():
            raise SnapshotError(f"Falta bce/{currency}.csv en la descarga {folder.name}")
        series = ecb_rates(path.read_text(encoding="utf-8"))
        rates += series
        if series:
            coverage.append(
                FxCoverage(currency, series[0].rate_date, series[-1].rate_date, len(series))
            )
    bundle = DataBundle(
        issuers=tuple(c.issuer() for c in universe.companies),
        equities=tuple(c.equity() for c in universe.companies),
        financial_facts=tuple(facts),
        equity_prices=tuple(prices),
        fx_rates=tuple(rates),
    )
    files = manifest.get("ficheros")
    entries = files if isinstance(files, list) else []
    sources = [(str(f["source"]), str(f["url"])) for f in entries if isinstance(f, dict)]
    return PublicDataResult(
        bundle=bundle,
        snapshot=folder,
        created=str(manifest.get("creado", "")),
        sources=sources,
        companies=companies,
        fx=coverage,
        with_prices=with_prices,
    )


class PublicDataProvider(DataProvider):
    """Real data of the study universe from a downloaded snapshot of public sources."""

    name: ClassVar[str] = "publico"

    def __init__(self, universe_path: Path, snapshot: Path) -> None:
        self.universe_path = universe_path
        self.snapshot = snapshot

    def build(self) -> PublicDataResult:
        return build(load_universe(self.universe_path), self.snapshot)

    def fetch(self) -> DataBundle:
        return self.build().bundle
