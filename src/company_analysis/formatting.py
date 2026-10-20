"""Spanish formatting of numbers and dates for the user interface (decimal comma, dd/mm/yyyy)."""

from datetime import date


def format_number(value: float, decimals: int = 1) -> str:
    """``1234.5`` -> ``"1.234,5"``."""
    text = f"{value:,.{decimals}f}"
    return text.replace(",", "\0").replace(".", ",").replace("\0", ".")


def format_date(day: date) -> str:
    return day.strftime("%d/%m/%Y")


def format_money(value_mn: float, currency: str, decimals: int = 1) -> str:
    """Amount in millions: ``"1.234,5 M EUR"``."""
    return f"{format_number(value_mn, decimals)} M {currency}"
