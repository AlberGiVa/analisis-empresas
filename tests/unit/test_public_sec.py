"""Point-in-time financial statements from SEC company facts (synthetic responses)."""

from datetime import date

import pytest

from company_analysis.models import FinancialFact, FinancialItem, FiscalPeriod
from company_analysis.providers.public.sec import (
    DebtLine,
    Extraction,
    FiscalCalendar,
    closes_fiscal_year,
    combine,
    extract_financials,
    publications,
    read_facts,
)
from tests import public_samples

DEBT = [
    DebtLine("Préstamos a corto plazo", ("ShortTermBorrowings",)),
    DebtLine("Deuda a largo plazo", ("LongTermDebtNoncurrent",), required=True),
]


@pytest.fixture(scope="module")
def extraction() -> Extraction:
    return extract_financials(
        "ZZAA",
        public_samples.companyfacts(),
        currency="USD",
        fiscal_year_end_month=12,
        debt_lines=DEBT,
    )


def facts_of(
    extraction: Extraction, item: FinancialItem, period: FiscalPeriod, end: date
) -> list[FinancialFact]:
    return sorted(
        (
            f
            for f in extraction.facts
            if (f.item, f.fiscal_period, f.period_end) == (item, period, end)
        ),
        key=lambda f: f.published_at,
    )


def test_periods_are_cumulative_from_the_start_of_the_fiscal_year() -> None:
    calendar = FiscalCalendar(public_samples.companyfacts(), 12)
    assert calendar.classify(date(2026, 1, 1), date(2026, 3, 31)) is FiscalPeriod.Q1
    assert calendar.classify(date(2026, 1, 1), date(2026, 6, 30)) is FiscalPeriod.H1
    assert calendar.classify(date(2025, 1, 1), date(2025, 12, 31)) is FiscalPeriod.FY
    assert calendar.classify(date(2026, 4, 1), date(2026, 6, 30)) is None  # a lone quarter
    # Twelve months ending in September are not a fiscal year of a December company.
    assert date(2024, 10, 1) not in calendar.year_starts


def test_fiscal_year_ends_tolerate_52_53_week_calendars() -> None:
    assert closes_fiscal_year(date(2025, 12, 27), 12)  # last Saturday of December
    assert closes_fiscal_year(date(2026, 1, 2), 12)
    assert closes_fiscal_year(date(2026, 5, 31), 5)
    assert not closes_fiscal_year(date(2025, 9, 30), 12)


def test_values_carry_the_date_their_report_was_filed(extraction: Extraction) -> None:
    (revenue,) = facts_of(extraction, FinancialItem.REVENUE, FiscalPeriod.H1, date(2026, 6, 30))
    assert revenue.value == 580.0
    assert revenue.published_at == date(2026, 7, 31)
    assert all(f.published_at >= f.period_end for f in extraction.facts)


def test_comparatives_are_not_new_publications(extraction: Extraction) -> None:
    # FY 2024 revenue appears in the 2024 and 2025 annual reports with the same value.
    published = facts_of(extraction, FinancialItem.REVENUE, FiscalPeriod.FY, date(2024, 12, 31))
    assert [(f.published_at, f.value) for f in published] == [(date(2025, 2, 14), 1030.0)]


def test_a_restated_value_is_kept_as_a_later_publication(extraction: Extraction) -> None:
    published = facts_of(extraction, FinancialItem.EBIT, FiscalPeriod.FY, date(2024, 12, 31))
    assert [f.published_at for f in published] == [date(2025, 2, 14), date(2026, 2, 13)]
    assert [f.value for f in published] == pytest.approx([206.0, 200.0])


def test_the_tag_that_reaches_the_latest_period_is_used_for_every_period(
    extraction: Extraction,
) -> None:
    lineage = {entry.item: entry for entry in extraction.lineage}
    assert lineage[FinancialItem.INTEREST_EXPENSE].source == "InterestExpenseNonoperating"
    assert lineage[FinancialItem.INTEREST_EXPENSE].latest == (FiscalPeriod.H1, date(2026, 6, 30))


def test_ebitda_is_operating_income_plus_depreciation(extraction: Extraction) -> None:
    (ebitda,) = facts_of(extraction, FinancialItem.EBITDA, FiscalPeriod.H1, date(2026, 6, 30))
    ebit = 0.2 * 280 + public_samples.IMPAIRED_QUARTER_EBIT
    depreciation = 0.05 * 580
    assert ebitda.value == pytest.approx(ebit + depreciation)


def test_cover_page_shares_belong_to_the_period_of_their_report(extraction: Extraction) -> None:
    (shares,) = facts_of(
        extraction, FinancialItem.SHARES_OUTSTANDING, FiscalPeriod.H1, date(2026, 6, 30)
    )
    assert (shares.value, shares.currency) == (100.0, None)
    lineage = {entry.item: entry for entry in extraction.lineage}
    assert lineage[FinancialItem.SHARES_OUTSTANDING].note is not None


def test_debt_lines_not_presented_count_as_zero(extraction: Extraction) -> None:
    (annual,) = facts_of(extraction, FinancialItem.TOTAL_DEBT, FiscalPeriod.FY, date(2025, 12, 31))
    (interim,) = facts_of(extraction, FinancialItem.TOTAL_DEBT, FiscalPeriod.H1, date(2026, 6, 30))
    assert (annual.value, interim.value) == (450.0, 400.0)
    latest = extraction.debt_breakdown[date(2026, 6, 30)]
    assert [(c.tag, c.value) for c in latest] == [(None, None), ("LongTermDebtNoncurrent", 400.0)]


def test_an_item_the_company_never_reports_is_missing_not_zero() -> None:
    facts = public_samples.companyfacts()
    del facts["facts"]["us-gaap"]["PaymentsToAcquirePropertyPlantAndEquipment"]
    result = extract_financials(
        "ZZAA", facts, currency="USD", fiscal_year_end_month=12, debt_lines=DEBT
    )
    assert not [f for f in result.facts if f.item is FinancialItem.CAPITAL_EXPENDITURE]
    lineage = {entry.item: entry for entry in result.lineage}
    assert lineage[FinancialItem.CAPITAL_EXPENDITURE].latest is None


def test_publications_keep_the_first_value_and_each_change() -> None:
    occurrences = [
        (date(2025, 2, 1), "a", 10.0),
        (date(2026, 2, 1), "c", 10.0),  # comparative: same value
        (date(2026, 2, 1), "b", 11.0),  # same day, earlier accession: counts
        (date(2026, 3, 1), "d", 12.0),
    ]
    assert publications(occurrences) == [
        (date(2025, 2, 1), 10.0),
        (date(2026, 2, 1), 11.0),
        (date(2026, 3, 1), 12.0),
    ]


def test_combine_sums_what_was_known_on_each_date() -> None:
    key = (FiscalPeriod.FY, date(2025, 12, 31))
    required = {key: [(date(2026, 2, 1), 100.0), (date(2026, 5, 1), 90.0)]}
    optional = {key: [(date(2026, 3, 1), 5.0)]}
    assert combine([required, optional], [False, True]) == {
        key: [(date(2026, 2, 1), 100.0), (date(2026, 3, 1), 105.0), (date(2026, 5, 1), 95.0)]
    }
    assert combine([optional, {}], [False, False]) == {}


def test_only_periodic_reports_are_read() -> None:
    """Proxy statements and 8-K exhibits repeat figures (rounded or recast): they are not new
    publications of the financial statements."""
    entry = {"start": "2025-01-01", "end": "2025-12-31", "val": 100.0, "filed": "2026-02-10"}
    companyfacts = {"facts": {"us-gaap": {"NetIncomeLoss": {"units": {"USD": [
        {**entry, "form": "10-K", "accn": "a"},
        {**entry, "val": 99.0, "form": "DEF 14A", "filed": "2026-03-20", "accn": "b"},
        {**entry, "val": 98.0, "form": "8-K", "filed": "2026-04-02", "accn": "c"},
        {**entry, "val": 101.0, "form": "10-K/A", "filed": "2026-05-15", "accn": "d"},
    ]}}}}}  # fmt: skip
    facts = read_facts(companyfacts, "NetIncomeLoss")
    assert [(f.form, f.value) for f in facts] == [("10-K", 100.0), ("10-K/A", 101.0)]
