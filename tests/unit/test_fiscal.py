from datetime import date

import pytest

from company_analysis.normalization import (
    add_months,
    comparable_year,
    fiscal_year_end,
    ltm_window_start,
)


@pytest.mark.parametrize(
    ("day", "months", "expected"),
    [
        (date(2025, 1, 15), 1, date(2025, 2, 15)),
        (date(2025, 1, 31), 1, date(2025, 2, 28)),  # clipped to the shorter month
        (date(2024, 3, 31), -1, date(2024, 2, 29)),  # month end stays month end (leap year)
        (date(2024, 2, 29), 12, date(2025, 2, 28)),
        (date(2025, 6, 30), -6, date(2024, 12, 31)),
        (date(2025, 12, 31), -12, date(2024, 12, 31)),
    ],
)
def test_add_months(day: date, months: int, expected: date) -> None:
    assert add_months(day, months) == expected


def test_ltm_window_covers_twelve_months() -> None:
    assert ltm_window_start(date(2025, 12, 31)) == date(2025, 1, 1)
    assert ltm_window_start(date(2026, 3, 31)) == date(2025, 4, 1)


@pytest.mark.parametrize(
    ("period_end", "year"),
    [
        (date(2025, 12, 31), 2025),
        (date(2025, 6, 30), 2025),  # June: six months in each year, assigned to the closing year
        (date(2026, 5, 31), 2025),
        (date(2026, 3, 31), 2025),  # April 2025 - March 2026: nine months fall in 2025
    ],
)
def test_comparable_year_is_where_most_months_fall(period_end: date, year: int) -> None:
    assert comparable_year(period_end) == year


@pytest.mark.parametrize(
    ("month", "expected"),
    [(12, date(2025, 12, 31)), (6, date(2025, 6, 30)), (3, date(2026, 3, 31))],
)
def test_fiscal_year_end_is_the_inverse_of_comparable_year(month: int, expected: date) -> None:
    assert fiscal_year_end(2025, month) == expected
    assert comparable_year(expected) == 2025
