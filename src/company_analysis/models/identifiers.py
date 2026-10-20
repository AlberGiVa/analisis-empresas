"""Validated identifiers and codes: ISIN, LEI, ISO 4217 currencies and ISO 3166 countries."""

import re
from typing import Annotated

from pydantic import AfterValidator, StringConstraints

BASE_CURRENCY = "EUR"

SUPPORTED_CURRENCIES = frozenset(
    {"EUR", "USD", "GBP", "CHF", "SEK", "NOK", "DKK", "PLN", "CZK", "HUF", "JPY", "CAD", "AUD"}
)

# European countries and the United States (initial universe of the fund).
SUPPORTED_COUNTRIES = frozenset(
    {
        "AT", "BE", "CH", "CZ", "DE", "DK", "ES", "FI", "FR", "GB", "GR",
        "HU", "IE", "IT", "LU", "NL", "NO", "PL", "PT", "SE", "US",
    }
)  # fmt: skip

_ISIN_PATTERN = re.compile(r"[A-Z]{2}[A-Z0-9]{9}[0-9]")
_LEI_PATTERN = re.compile(r"[A-Z0-9]{18}[0-9]{2}")


def _letters_to_digits(text: str) -> str:
    """Replace each letter by its number (A=10 … Z=35), as ISIN and LEI check digits require."""
    return "".join(str(int(char, 36)) for char in text)


def isin_check_digit(body: str) -> int:
    """Check digit for the first 11 characters of an ISIN (Luhn over the expanded digits)."""
    total = 0
    for position, char in enumerate(reversed(_letters_to_digits(body))):
        value = int(char)
        if position % 2 == 0:  # double every other digit, starting with the rightmost one
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return (10 - total % 10) % 10


def lei_check_digits(body: str) -> str:
    """Two check digits for the first 18 characters of an LEI (ISO 7064 MOD 97-10)."""
    remainder = int(_letters_to_digits(body + "00")) % 97
    return f"{98 - remainder:02d}"


def _validate_isin(value: str) -> str:
    if not _ISIN_PATTERN.fullmatch(value) or isin_check_digit(value[:11]) != int(value[11]):
        raise ValueError(f"ISIN no válido: {value!r}")
    return value


def _validate_lei(value: str) -> str:
    if not _LEI_PATTERN.fullmatch(value) or int(_letters_to_digits(value)) % 97 != 1:
        raise ValueError(f"LEI no válido: {value!r}")
    return value


def _validate_currency(value: str) -> str:
    if value not in SUPPORTED_CURRENCIES:
        raise ValueError(f"Divisa no admitida: {value!r}")
    return value


def _validate_country(value: str) -> str:
    if value not in SUPPORTED_COUNTRIES:
        raise ValueError(f"País no admitido: {value!r}")
    return value


Isin = Annotated[str, AfterValidator(_validate_isin)]
Lei = Annotated[str, AfterValidator(_validate_lei)]
CurrencyCode = Annotated[str, AfterValidator(_validate_currency)]
CountryCode = Annotated[str, AfterValidator(_validate_country)]
IssuerId = Annotated[str, StringConstraints(pattern=r"^[A-Z0-9]{2,12}$")]
