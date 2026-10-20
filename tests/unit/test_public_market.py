"""Share prices and exchange rates from the public services (synthetic responses)."""

from datetime import date

import pytest

from company_analysis.providers.public.market import (
    ecb_rates,
    nasdaq_prices,
    price_differences,
    yahoo_closes,
    yahoo_exchange,
)
from company_analysis.providers.sample_generator import equity_isin
from tests import public_samples

ISIN = equity_isin("ZZAA")
DAYS = [date(2026, 8, 12), date(2026, 8, 13), date(2026, 8, 14)]


def test_nasdaq_prices_parse_dollar_amounts_and_us_dates() -> None:
    payload = {"data": {"tradesTable": {"rows": [
        {"date": "08/14/2026", "close": "$1,234.56"},
        {"date": "08/13/2026", "close": "N/A"},
        {"date": "08/12/2026", "close": "$1,200.00"},
    ]}}}  # fmt: skip
    prices = nasdaq_prices(payload, isin=ISIN, currency="USD")
    assert [(p.price_date, p.close) for p in prices] == [
        (date(2026, 8, 12), 1200.0),
        (date(2026, 8, 14), 1234.56),
    ]


def test_yahoo_closes_use_the_exchange_trading_day() -> None:
    payload = public_samples.yahoo(DAYS, 50.0)
    assert yahoo_closes(payload) == {DAYS[0]: 50.0, DAYS[1]: 50.01, DAYS[2]: 50.02}
    assert yahoo_exchange(payload) == "NYQ"
    assert yahoo_closes({}) == {}


def test_ecb_rates_are_units_per_euro() -> None:
    rates = ecb_rates(public_samples.ecb_csv(DAYS, 1.1225))
    first = rates[0]
    assert (first.currency, first.rate_date, first.units_per_eur) == ("USD", DAYS[0], 1.1225)


def test_price_differences_against_a_second_source() -> None:
    prices = nasdaq_prices(public_samples.nasdaq(DAYS, 50.0), isin=ISIN, currency="USD")
    reference = {DAYS[0]: 50.0, DAYS[1]: 50.01, DAYS[2]: 51.0}
    compared, worst, day = price_differences(prices, reference)
    assert compared == 3
    assert worst == pytest.approx(abs(50.02 / 51.0 - 1))
    assert day == DAYS[2]
