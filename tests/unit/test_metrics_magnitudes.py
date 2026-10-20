"""Absolute magnitudes converted into euros with the documented rates."""

import pytest

from company_analysis.figures import Figure, Status
from company_analysis.models import FinancialItem as Item
from tests import factories
from tests.snapshots import compute, snapshot

USD_COMPANY = snapshot(
    issuer=factories.issuer(currency="USD", country="US"),
    market_cap=1100.0,
    flows={Item.REVENUE: 2200.0, Item.EBITDA: 440.0},
    stocks={Item.TOTAL_DEBT: 330.0, Item.CASH: 110.0},
    eur_average_rate=1.10,  # USD per EUR over the LTM window
    eur_closing_rate=1.10,  # at the period close
    eur_spot_rate=1.10,  # at the price date
)


@pytest.mark.parametrize(
    ("metric_id", "expected"),
    [
        ("market_cap_eur", 1000.0),  # 1100 / 1.10
        ("enterprise_value_eur", 1200.0),  # (1100 + 330 - 110) / 1.10
        ("revenue_ltm_eur", 2000.0),  # 2200 / 1.10
        ("ebitda_ltm_eur", 400.0),  # 440 / 1.10
        ("net_debt_eur", 200.0),  # (330 - 110) / 1.10
    ],
)
def test_magnitudes_in_euros(metric_id: str, expected: float) -> None:
    assert compute(metric_id, USD_COMPANY).value == pytest.approx(expected)


def test_each_magnitude_uses_its_own_rate() -> None:
    s = snapshot(
        flows={Item.REVENUE: 2200.0},
        stocks={Item.TOTAL_DEBT: 330.0, Item.CASH: 110.0},
        market_cap=1100.0,
        eur_average_rate=1.0,
        eur_closing_rate=2.0,
        eur_spot_rate=4.0,
    )
    assert compute("revenue_ltm_eur", s).value == pytest.approx(2200.0)
    assert compute("net_debt_eur", s).value == pytest.approx(110.0)
    assert compute("market_cap_eur", s).value == pytest.approx(275.0)


def test_magnitude_without_exchange_rate_is_missing() -> None:
    no_rate = Figure.unavailable("Tipo de cambio", Status.MISSING, "sin tipo de cambio")
    s = snapshot(market_cap=1100.0, eur_spot_rate=no_rate)
    assert compute("market_cap_eur", s).status is Status.MISSING
