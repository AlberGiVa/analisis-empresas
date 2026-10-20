from datetime import date

import pytest

from company_analysis.figures import Status
from company_analysis.models import FinancialFact, FinancialItem, FiscalPeriod
from company_analysis.normalization import IssuerFacts
from tests import factories

REVENUE = FinancialItem.REVENUE


def revenue(
    value: float, period_end: date, period: FiscalPeriod = FiscalPeriod.FY
) -> FinancialFact:
    return factories.fact(
        REVENUE, value, period_end=period_end, published_at=period_end, fiscal_period=period
    )


@pytest.fixture
def facts() -> IssuerFacts:
    return IssuerFacts(
        [
            revenue(950.0, date(2023, 12, 31)),
            revenue(450.0, date(2023, 6, 30), FiscalPeriod.H1),
            revenue(480.0, date(2024, 6, 30), FiscalPeriod.H1),
            revenue(1000.0, date(2024, 12, 31)),
            revenue(550.0, date(2025, 6, 30), FiscalPeriod.H1),
        ]
    )


def test_reference_period_is_the_latest_reported(facts: IssuerFacts) -> None:
    reference = facts.reference_period()
    assert reference is not None
    assert (reference.fiscal_period, reference.period_end) == (FiscalPeriod.H1, date(2025, 6, 30))


def test_full_year_wins_over_an_interim_period_ending_the_same_day() -> None:
    reference = IssuerFacts(
        [
            revenue(800.0, date(2024, 12, 31), FiscalPeriod.NINE_MONTHS),
            revenue(1000.0, date(2024, 12, 31)),
        ]
    ).reference_period()
    assert reference is not None
    assert reference.fiscal_period is FiscalPeriod.FY


def test_ltm_of_a_full_year_is_the_reported_value(facts: IssuerFacts) -> None:
    assert facts.ltm(REVENUE, FiscalPeriod.FY, date(2024, 12, 31)).value == 1000.0


def test_ltm_of_an_interim_period(facts: IssuerFacts) -> None:
    # FY 2024 + H1 2025 - H1 2024 = 1000 + 550 - 480
    assert facts.ltm(REVENUE, FiscalPeriod.H1, date(2025, 6, 30)).value == 1070.0
    # One year earlier: FY 2023 + H1 2024 - H1 2023 = 950 + 480 - 450
    assert facts.ltm(REVENUE, FiscalPeriod.H1, date(2024, 6, 30)).value == 980.0


def test_ltm_is_missing_when_a_component_is_missing() -> None:
    facts = IssuerFacts(
        [revenue(1000.0, date(2024, 12, 31)), revenue(550.0, date(2025, 6, 30), FiscalPeriod.H1)]
    )
    result = facts.ltm(REVENUE, FiscalPeriod.H1, date(2025, 6, 30))
    assert result.status is Status.MISSING
    assert result.detail is not None
    assert "H1 30/06/2024" in result.detail


def test_closing_dates_a_few_days_apart_are_the_same_period() -> None:
    facts = IssuerFacts(
        [
            revenue(1000.0, date(2024, 12, 28)),  # 52/53-week calendar
            revenue(550.0, date(2025, 6, 28), FiscalPeriod.H1),
            revenue(480.0, date(2024, 6, 29), FiscalPeriod.H1),
        ]
    )
    assert facts.ltm(REVENUE, FiscalPeriod.H1, date(2025, 6, 28)).value == 1070.0


def test_the_latest_publication_of_a_value_is_used() -> None:
    original = revenue(1000.0, date(2024, 12, 31))
    restated = factories.fact(
        REVENUE, 1020.0, period_end=date(2024, 12, 31), published_at=date(2025, 9, 1)
    )
    assert (
        IssuerFacts([original, restated]).ltm(REVENUE, FiscalPeriod.FY, date(2024, 12, 31)).value
        == 1020.0
    )


def test_balance_is_the_value_at_the_period_close() -> None:
    debt = factories.fact(FinancialItem.TOTAL_DEBT, 300.0, period_end=date(2024, 12, 31))
    facts = IssuerFacts([debt])
    assert (
        facts.balance(FinancialItem.TOTAL_DEBT, FiscalPeriod.FY, date(2024, 12, 31)).value == 300.0
    )
    missing = facts.balance(FinancialItem.CASH, FiscalPeriod.FY, date(2024, 12, 31))
    assert missing.status is Status.MISSING


def test_ltm_with_quarters_of_12_and_16_weeks() -> None:
    # 52-week year closing on the last Saturday of December, quarters of 12, 12, 12 and 16 weeks:
    # the 36-week "9M" period ends in early September, three weeks after "December + 9 months".
    facts = IssuerFacts(
        [
            revenue(900.0, date(2024, 12, 28)),
            revenue(600.0, date(2024, 9, 7), FiscalPeriod.NINE_MONTHS),
            revenue(1000.0, date(2025, 12, 27)),
            revenue(660.0, date(2025, 9, 6), FiscalPeriod.NINE_MONTHS),
            revenue(700.0, date(2026, 9, 5), FiscalPeriod.NINE_MONTHS),
        ]
    )
    # FY 2025 + 9M 2026 - 9M 2025 = 1000 + 700 - 660
    assert facts.ltm(REVENUE, FiscalPeriod.NINE_MONTHS, date(2026, 9, 5)).value == 1040.0
    # One year earlier: FY 2024 + 9M 2025 - 9M 2024 = 900 + 660 - 600
    assert facts.ltm(REVENUE, FiscalPeriod.NINE_MONTHS, date(2025, 9, 6)).value == 960.0
