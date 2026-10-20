"""Fiscal calendar arithmetic and the alignment of fiscal years that do not end in December."""

import calendar
from datetime import date, timedelta

# Interim periods may close a few days apart from year to year (52/53-week calendars).
PERIOD_TOLERANCE = timedelta(days=7)


def _last_day(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def add_months(day: date, months: int) -> date:
    """Shift by whole months. Month ends map to month ends (31 March - 1 month = 28/29 February)."""
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    month += 1
    if day.day == _last_day(day.year, day.month):
        return date(year, month, _last_day(year, month))
    return date(year, month, min(day.day, _last_day(year, month)))


def ltm_window_start(period_end: date) -> date:
    """First day of the twelve months that end on ``period_end``."""
    return add_months(period_end, -12) + timedelta(days=1)


def comparable_year(period_end: date) -> int:
    """Calendar year a fiscal year is compared with: the one in which most of its months fall.

    A fiscal year that ends between June and December belongs to that same year; one that ends
    between January and May belongs to the previous year (a year ended in March 2026 compares
    with calendar 2025).
    """
    return period_end.year if period_end.month >= 6 else period_end.year - 1


def fiscal_year_end(year: int, fiscal_year_end_month: int) -> date:
    """Closing date of the fiscal year that compares with calendar year ``year``."""
    end_year = year if fiscal_year_end_month >= 6 else year + 1
    return date(end_year, fiscal_year_end_month, _last_day(end_year, fiscal_year_end_month))
