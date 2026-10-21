"""Financial statements from SEC EDGAR "company facts" (XBRL, US GAAP), point in time.

Each reported value keeps the date its filing was accepted ("filed"), so the analysis never uses a
figure before it was public. Values come out of every filing that repeats them (comparatives); a
value that changes in a later filing is a restatement and is kept as a later publication.

Periods are classified by their own dates, not by the label of the filing that contains them: an
annual report also carries the previous years, and a quarterly report both the quarter and the
year to date. Only cumulative periods from the start of the fiscal year are used (Q1, H1, 9M, FY).
"""

from calendar import monthrange
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from company_analysis.models import FinancialFact, FinancialItem, FiscalPeriod

MILLION = 1_000_000.0
YEAR_START_TOLERANCE = timedelta(days=3)
FISCAL_YEAR_END_TOLERANCE = timedelta(days=10)
# Length in days of each cumulative period (52/53-week calendars and 12/16-week quarters fit).
PERIOD_DAYS: dict[FiscalPeriod, tuple[int, int]] = {
    FiscalPeriod.Q1: (76, 100),
    FiscalPeriod.H1: (160, 200),
    FiscalPeriod.NINE_MONTHS: (240, 290),
    FiscalPeriod.FY: (350, 380),
}

PeriodKey = tuple[FiscalPeriod, date]
Series = dict[PeriodKey, list[tuple[date, float]]]  # publications (filed, value), oldest first


@dataclass(frozen=True)
class SecFact:
    """One occurrence of a reported value in one filing."""

    tag: str
    start: date | None  # None for balances (instants)
    end: date
    value: float
    filed: date
    accession: str
    form: str = ""


# Only periodic reports count: the same concepts also appear in proxy statements (DEF 14A pay
# versus performance tables, rounded) and in 8-K exhibits, which are not new publications of the
# financial statements and must not be read as restatements.
REPORT_FORMS = frozenset(
    {"10-K", "10-Q", "10-K/A", "10-Q/A", "10-KT", "10-QT", "10-KT/A", "10-QT/A"}
)


def read_facts(
    companyfacts: Mapping[str, Any], tag: str, *, taxonomy: str = "us-gaap", unit: str = "USD"
) -> list[SecFact]:
    """Every occurrence of ``taxonomy:tag`` in ``unit`` in a periodic report (10-K, 10-Q and their
    amendments); empty if the company never used it."""
    concept = companyfacts.get("facts", {}).get(taxonomy, {}).get(tag) or {}
    return [
        SecFact(
            tag=tag,
            start=date.fromisoformat(entry["start"]) if entry.get("start") else None,
            end=date.fromisoformat(entry["end"]),
            value=float(entry["val"]),
            filed=date.fromisoformat(entry["filed"]),
            accession=str(entry.get("accn", "")),
            form=str(entry.get("form", "")),
        )
        for entry in concept.get("units", {}).get(unit, [])
        if str(entry.get("form", "")) in REPORT_FORMS
    ]


def _days(start: date, end: date) -> int:
    return (end - start).days + 1


def closes_fiscal_year(day: date, fiscal_year_end_month: int) -> bool:
    """Whether ``day`` is a fiscal year end: the month's last day, or within ten days of it
    (calendars of 52/53 weeks close on a weekday near the end of the month)."""
    for year in (day.year - 1, day.year, day.year + 1):
        month_end = date(year, fiscal_year_end_month, monthrange(year, fiscal_year_end_month)[1])
        if abs(day - month_end) <= FISCAL_YEAR_END_TOLERANCE:
            return True
    return False


class FiscalCalendar:
    """Fiscal periods of one company, inferred from the full years of its annual reports.

    Only twelve-month periods that close at the company's fiscal year end count as years: annual
    reports sometimes also disclose other twelve-month periods (pro forma, trailing figures).
    """

    def __init__(self, companyfacts: Mapping[str, Any], fiscal_year_end_month: int) -> None:
        durations = [
            fact
            for tag in companyfacts.get("facts", {}).get("us-gaap", {})
            for fact in read_facts(companyfacts, tag)
            if fact.start is not None
        ]
        lo, hi = PERIOD_DAYS[FiscalPeriod.FY]
        years = {
            (fact.start, fact.end)
            for fact in durations
            if fact.start is not None and fact.form.startswith("10-K")
            and lo <= _days(fact.start, fact.end) <= hi
            and closes_fiscal_year(fact.end, fiscal_year_end_month)
        }  # fmt: skip
        self.year_starts = sorted({s for s, _ in years} | {e + timedelta(days=1) for _, e in years})
        self.period_ends: dict[date, FiscalPeriod] = {}  # closing date -> period (for balances)
        self.filing_period_end: dict[str, date] = {}  # accession -> period the filing reports
        for fact in durations:
            assert fact.start is not None
            period = self.classify(fact.start, fact.end)
            if period is None:
                continue
            if self.period_ends.get(fact.end) is not FiscalPeriod.FY:
                self.period_ends[fact.end] = period
            if fact.end > self.filing_period_end.get(fact.accession, date.min):
                self.filing_period_end[fact.accession] = fact.end

    def classify(self, start: date, end: date) -> FiscalPeriod | None:
        """Cumulative period from the start of a fiscal year, or None (e.g. a single quarter)."""
        if not any(abs(start - first) <= YEAR_START_TOLERANCE for first in self.year_starts):
            return None
        days = _days(start, end)
        return next((p for p, (lo, hi) in PERIOD_DAYS.items() if lo <= days <= hi), None)

    def period_of(self, fact: SecFact) -> FiscalPeriod | None:
        if fact.start is not None:
            return self.classify(fact.start, fact.end)
        return self.period_ends.get(fact.end)


def publications(occurrences: Iterable[tuple[date, str, float]]) -> list[tuple[date, float]]:
    """First publication of a value and every later change of it (restatements).

    ``occurrences`` are (filed, accession, value). Two filings on the same day: the first counts.
    """
    result: list[tuple[date, float]] = []
    for filed, _, value in sorted(occurrences):
        if result and (result[-1][1] == value or result[-1][0] == filed):
            continue
        result.append((filed, value))
    return result


def series_of(calendar: FiscalCalendar, facts: Iterable[SecFact], *, sign: float = 1.0) -> Series:
    """Publications of each period, in millions."""
    grouped: dict[PeriodKey, list[tuple[date, str, float]]] = defaultdict(list)
    for fact in facts:
        period = calendar.period_of(fact)
        if period is not None:
            value = sign * fact.value / MILLION
            grouped[(period, fact.end)].append((fact.filed, fact.accession, value))
    return {key: publications(values) for key, values in grouped.items()}


def combine(parts: Sequence[Series], optional: Sequence[bool] | None = None) -> Series:
    """Sum of several series, as it was known on each publication date.

    A required part missing for a period leaves the period out. An optional part missing for a
    period counts as zero there (a balance-sheet line the company did not present).
    """
    flags = list(optional) if optional is not None else [False] * len(parts)
    keys = {key for part, opt in zip(parts, flags, strict=True) if not opt for key in part}
    result: Series = {}
    for key in keys:
        series = [part.get(key, []) for part in parts]
        out: list[tuple[date, float]] = []
        for day in sorted({filed for s in series for filed, _ in s}):
            known = [[value for filed, value in s if filed <= day] for s in series]
            if any(not k and not opt for k, opt in zip(known, flags, strict=True)):
                continue
            total = sum(k[-1] for k in known if k)
            if not out or out[-1][1] != total:
                out.append((day, total))
        if out:
            result[key] = out
    return result


def latest_period(series: Series) -> PeriodKey | None:
    """Most recent period (a full year wins over an interim period closing the same day)."""
    return max(series, key=lambda key: (key[1], key[0] is FiscalPeriod.FY), default=None)


# --- Where each item comes from ------------------------------------------------------------------
@dataclass(frozen=True)
class Source:
    """One way of obtaining an item: a tag, or a signed sum of tags from the same statements."""

    terms: tuple[tuple[str, float], ...]  # (tag, sign)
    taxonomy: str = "us-gaap"
    unit: str = "USD"
    note: str | None = None  # a fallback the analyst should know about (shown in the lineage)

    @property
    def label(self) -> str:
        text = ""
        for index, (tag, sign) in enumerate(self.terms):
            if index:
                text += " − " if sign < 0 else " + "
            elif sign < 0:
                text += "−"
            text += tag
        return text


def tags(*names: str, note: str | None = None, unit: str = "USD") -> tuple[Source, ...]:
    """One source per tag, in priority order."""
    return tuple(Source(((name, 1.0),), unit=unit, note=note) for name in names)


ITEM_SOURCES: dict[FinancialItem, tuple[Source, ...]] = {
    FinancialItem.REVENUE: tags(
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
    ),
    FinancialItem.GROSS_PROFIT: tags("GrossProfit"),
    FinancialItem.EBIT: tags("OperatingIncomeLoss"),
    FinancialItem.INTEREST_EXPENSE: (
        *tags(
            "InterestExpense",
            "InterestExpenseNonoperating",
            "InterestExpenseDebt",
            "InterestAndDebtExpense",
        ),
        Source(
            (("InterestIncomeExpenseNonoperatingNet", -1.0),),
            note="gasto financiero neto de ingresos financieros: la empresa no publica el bruto",
        ),
    ),
    FinancialItem.NET_INCOME: tags("NetIncomeLoss"),
    FinancialItem.OPERATING_CASH_FLOW: tags(
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ),
    FinancialItem.CAPITAL_EXPENDITURE: tags(
        "PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"
    ),
    FinancialItem.CASH: (
        *tags("CashAndCashEquivalentsAtCarryingValue"),
        *tags(
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
            note="incluye caja restringida: la empresa no publica la caja sin ella",
        ),
    ),
    FinancialItem.TOTAL_EQUITY: (
        *tags("StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
        *tags(
            "StockholdersEquity",
            note="sin minoritarios: la empresa no publica el patrimonio con ellos",
        ),
    ),
    FinancialItem.EQUITY_ATTRIBUTABLE: (
        *tags("StockholdersEquity"),
        Source(
            (
                ("StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", 1.0),
                ("MinorityInterest", -1.0),
            ),
            note="calculado: patrimonio total menos minoritarios",
        ),
    ),
    FinancialItem.SHARES_OUTSTANDING: (
        *tags("CommonStockSharesOutstanding", unit="shares"),
        Source(
            (("EntityCommonStockSharesOutstanding", 1.0),),
            taxonomy="dei",
            unit="shares",
            note="acciones de la portada del informe, a una fecha algo posterior al cierre",
        ),
    ),
}
DEPRECIATION_SOURCES: tuple[Source, ...] = (
    *tags(
        "DepreciationDepletionAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
        "DepreciationAndAmortization",
    ),
    Source((("Depreciation", 1.0), ("AmortizationOfIntangibleAssets", 1.0))),
)


@dataclass(frozen=True)
class DebtLine:
    """A balance-sheet line that is part of financial debt, as the company presents it."""

    label: str
    tags: tuple[str, ...]  # alternatives: the same line may carry another tag in some reports
    required: bool = False


@dataclass(frozen=True)
class Lineage:
    """Where an item comes from, for the data-quality report."""

    item: FinancialItem
    source: str
    note: str | None
    latest: PeriodKey | None
    restatements: int


@dataclass(frozen=True)
class DebtComponent:
    line: str
    tag: str | None  # None: the line is not presented on that balance sheet (counts as zero)
    value: float | None


@dataclass
class Extraction:
    facts: list[FinancialFact] = field(default_factory=list)
    lineage: list[Lineage] = field(default_factory=list)
    debt_breakdown: dict[date, list[DebtComponent]] = field(default_factory=dict)


def _source_facts(
    calendar: FiscalCalendar, companyfacts: Mapping[str, Any], tag: str, source: Source
) -> list[SecFact]:
    facts = read_facts(companyfacts, tag, taxonomy=source.taxonomy, unit=source.unit)
    if source.taxonomy != "dei":
        return facts
    # Cover-page counts are dated after the period: attach each one to the period of its report.
    return [
        SecFact(fact.tag, None, end, fact.value, fact.filed, fact.accession, fact.form)
        for fact in facts
        if (end := calendar.filing_period_end.get(fact.accession)) is not None
    ]


def source_series(
    calendar: FiscalCalendar, companyfacts: Mapping[str, Any], source: Source
) -> Series:
    parts = [
        series_of(calendar, _source_facts(calendar, companyfacts, tag, source), sign=sign)
        for tag, sign in source.terms
    ]
    return parts[0] if len(parts) == 1 else combine(parts)


def choose_source(
    calendar: FiscalCalendar, companyfacts: Mapping[str, Any], sources: Sequence[Source]
) -> tuple[Source, Series] | None:
    """The source that reaches the most recent period (the first in priority order on a tie).

    One source per item and company, used for every period: mixing tags across periods could make
    a twelve-month figure add up two different definitions.
    """
    best: tuple[Source, Series, date] | None = None
    for source in sources:
        series = source_series(calendar, companyfacts, source)
        latest = latest_period(series)
        if latest is not None and (best is None or latest[1] > best[2]):
            best = (source, series, latest[1])
    return (best[0], best[1]) if best else None


def _lineage(item: FinancialItem, source: str, note: str | None, series: Series) -> Lineage:
    restated = sum(len(published) - 1 for published in series.values())
    return Lineage(item, source, note, latest_period(series), restated)


def _debt_line(
    calendar: FiscalCalendar, companyfacts: Mapping[str, Any], line: DebtLine
) -> tuple[Series, dict[PeriodKey, str]]:
    """One debt line: on each balance sheet, the first of its alternative tags with a value."""
    merged: Series = {}
    used: dict[PeriodKey, str] = {}
    for tag in line.tags:
        for key, published in series_of(calendar, read_facts(companyfacts, tag)).items():
            if key not in merged:
                merged[key], used[key] = published, tag
    return merged, used


def extract_financials(
    issuer_id: str,
    companyfacts: Mapping[str, Any],
    *,
    currency: str,
    fiscal_year_end_month: int,
    debt_lines: Sequence[DebtLine],
    overrides: Mapping[FinancialItem, Sequence[str]] | None = None,
    depreciation_tags: Sequence[str] = (),
) -> Extraction:
    """Every catalogue item of one company, with its publication dates and its lineage.

    ``depreciation_tags`` replaces the default depreciation sources of the EBITDA with the sum of
    those tags (for a company whose usual tag leaves out part of its amortisation).
    """
    calendar = FiscalCalendar(companyfacts, fiscal_year_end_month)
    result = Extraction()
    chosen: dict[FinancialItem, Series] = {}
    for item, default_sources in ITEM_SOURCES.items():
        sources = default_sources
        if overrides and item in overrides:
            unit = "USD" if item.is_monetary else "shares"
            sources = tags(*overrides[item], note="etiqueta fijada en el universo", unit=unit)
        found = choose_source(calendar, companyfacts, sources)
        if found is None:
            result.lineage.append(Lineage(item, "—", "la empresa no publica esta partida", None, 0))
            continue
        source, series = found
        chosen[item] = series
        result.lineage.append(_lineage(item, source.label, source.note, series))

    # EBITDA = operating income (EBIT) + depreciation and amortisation, both as published.
    depreciation_sources = DEPRECIATION_SOURCES
    if depreciation_tags:
        depreciation_sources = (Source(tuple((tag, 1.0) for tag in depreciation_tags)),)
    depreciation = choose_source(calendar, companyfacts, depreciation_sources)
    if FinancialItem.EBIT in chosen and depreciation is not None:
        ebitda = combine([chosen[FinancialItem.EBIT], depreciation[1]])
        chosen[FinancialItem.EBITDA] = ebitda
        result.lineage.append(
            _lineage(
                FinancialItem.EBITDA,
                f"OperatingIncomeLoss + {depreciation[0].label}",
                "calculado: resultado operativo publicado más las amortizaciones fijadas en el "
                "universo"
                if depreciation_tags
                else "calculado: resultado operativo publicado más amortizaciones del estado de "
                "flujos",
                ebitda,
            )
        )
    else:
        result.lineage.append(
            Lineage(
                FinancialItem.EBITDA,
                "—",
                "falta el resultado operativo o las amortizaciones",
                None,
                0,
            )
        )

    # Financial debt: the balance-sheet lines listed for the company in the universe file.
    lines = [_debt_line(calendar, companyfacts, line) for line in debt_lines]
    debt = combine([series for series, _ in lines], [not line.required for line in debt_lines])
    if debt:
        chosen[FinancialItem.TOTAL_DEBT] = debt
        result.lineage.append(
            _lineage(
                FinancialItem.TOTAL_DEBT,
                " + ".join(line.label for line in debt_lines),
                "líneas de deuda del balance; una línea que no aparece en un balance cuenta "
                "como cero",
                debt,
            )
        )
        for key in sorted(debt, key=lambda k: k[1])[-2:]:
            result.debt_breakdown[key[1]] = [
                DebtComponent(
                    line.label, used.get(key), series[key][-1][1] if key in series else None
                )
                for line, (series, used) in zip(debt_lines, lines, strict=True)
            ]
    else:
        result.lineage.append(
            Lineage(
                FinancialItem.TOTAL_DEBT, "—", "no aparece la línea de deuda obligatoria", None, 0
            )
        )

    for item, series in chosen.items():
        result.facts.extend(
            FinancialFact(
                issuer_id=issuer_id,
                fiscal_period=period,
                period_end=end,
                item=item,
                value=value,
                currency=currency if item.is_monetary else None,
                published_at=filed,
            )
            for (period, end), published in sorted(series.items())
            for filed, value in published
            if filed >= end
        )
    return result
