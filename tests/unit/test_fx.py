from datetime import date

import pytest

from company_analysis.figures import Status
from company_analysis.normalization import FxTable
from tests import factories


@pytest.fixture
def table() -> FxTable:
    return FxTable(
        [
            factories.fx("USD", date(2025, 1, 2), 1.10),
            factories.fx("USD", date(2025, 1, 3), 1.12),
            factories.fx("USD", date(2025, 1, 6), 1.08),
            factories.fx("GBP", date(2025, 1, 3), 0.84),
        ],
        max_age_days=7,
    )


def test_rate_is_the_latest_available_on_or_before_the_date(table: FxTable) -> None:
    assert table.rate("USD", date(2025, 1, 4)).value == 1.12  # Saturday: Friday's rate
    assert table.rate("USD", date(2025, 1, 6)).value == 1.08


def test_euro_rate_is_one(table: FxTable) -> None:
    assert table.rate("EUR", date(2025, 1, 4)).value == 1.0


def test_rate_older_than_the_limit_is_missing(table: FxTable) -> None:
    rate = table.rate("USD", date(2025, 1, 20))  # 14 days after the last rate
    assert rate.status is Status.MISSING
    assert rate.detail is not None
    assert "sin tipo de cambio" in rate.detail
    assert table.rate("CHF", date(2025, 1, 3)).status is Status.MISSING


def test_average_uses_the_rates_inside_the_window(table: FxTable) -> None:
    assert table.average("USD", date(2025, 1, 1), date(2025, 1, 5)).value == pytest.approx(1.11)
    assert table.average("USD", date(2025, 2, 1), date(2025, 2, 28)).status is Status.MISSING


def test_cross_rate_goes_through_the_euro(table: FxTable) -> None:
    # 1 EUR = 1.12 USD = 0.84 GBP, so 1 USD = 0.84 / 1.12 GBP = 0.75 GBP
    assert table.cross("USD", "GBP", date(2025, 1, 3)).value == pytest.approx(0.75)
    assert table.cross("EUR", "USD", date(2025, 1, 3)).value == pytest.approx(1.12)
    assert table.cross("USD", "USD", date(2025, 1, 3)).value == 1.0
