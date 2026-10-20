import pytest
from pydantic import TypeAdapter, ValidationError

from company_analysis.models.identifiers import (
    CountryCode,
    CurrencyCode,
    Isin,
    Lei,
    isin_check_digit,
    lei_check_digits,
)
from company_analysis.providers.sample_generator import synthetic_isin, synthetic_lei


@pytest.mark.parametrize(
    ("isin", "check_digit"),
    [
        ("US0378331005", 5),  # Apple Inc. (public identifier, used only to test the algorithm)
        ("DE0007164600", 0),  # SAP SE
    ],
)
def test_isin_check_digit_matches_real_identifiers(isin: str, check_digit: int) -> None:
    assert isin_check_digit(isin[:11]) == check_digit
    assert TypeAdapter(Isin).validate_python(isin) == isin


@pytest.mark.parametrize(
    "lei",
    [
        "506700GE1G29325QX363",  # GLEIF (public identifier)
        "HWUPKR0MPOU8FGXBT394",  # Apple Inc.
    ],
)
def test_lei_check_digits_match_real_identifiers(lei: str) -> None:
    assert lei_check_digits(lei[:18]) == lei[18:]
    assert TypeAdapter(Lei).validate_python(lei) == lei


@pytest.mark.parametrize(
    "value",
    ["US0378331006", "US037833100", "us0378331005"],
)
def test_invalid_isins_are_rejected(value: str) -> None:
    with pytest.raises(ValidationError, match="ISIN no válido"):
        TypeAdapter(Isin).validate_python(value)


def test_invalid_lei_is_rejected() -> None:
    with pytest.raises(ValidationError, match="LEI no válido"):
        TypeAdapter(Lei).validate_python("506700GE1G29325QX364")


def test_synthetic_identifiers_are_valid_and_recognisable() -> None:
    isin = synthetic_isin("E", "ABCD")
    lei = synthetic_lei("ABCD")
    assert isin.startswith("ZZ")
    assert lei.startswith("ZZZZ")
    assert TypeAdapter(Isin).validate_python(isin) == isin
    assert TypeAdapter(Lei).validate_python(lei) == lei


def test_unsupported_currency_and_country_are_rejected() -> None:
    with pytest.raises(ValidationError, match="Divisa no admitida"):
        TypeAdapter(CurrencyCode).validate_python("XXX")
    with pytest.raises(ValidationError, match="País no admitido"):
        TypeAdapter(CountryCode).validate_python("ZZ")
