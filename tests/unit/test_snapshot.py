"""Normalisation into company snapshots: periods, look-ahead, staleness and currencies."""

from datetime import date

import pytest

from company_analysis.config import NormalizationConfig
from company_analysis.figures import Status
from company_analysis.models import DataBundle, FinancialFact, FinancialItem
from company_analysis.normalization import CompanySnapshot, build_snapshots
from tests import factories

AS_OF = date(2025, 6, 30)
FY2023, FY2024 = date(2023, 12, 31), date(2024, 12, 31)


def statements(
    period_end: date,
    *,
    revenue: float = 1000.0,
    currency: str = "EUR",
    published_at: date | None = None,
) -> list[FinancialFact]:
    values = {
        FinancialItem.REVENUE: revenue,
        FinancialItem.EBITDA: 200.0,
        FinancialItem.NET_INCOME: 90.0,
        FinancialItem.TOTAL_DEBT: 400.0,
        FinancialItem.CASH: 100.0,
        FinancialItem.SHARES_OUTSTANDING: 10.0,
    }
    return [
        factories.fact(
            item,
            value,
            period_end=period_end,
            published_at=published_at or date(period_end.year + 1, 2, 15),
            currency=currency,
        )
        for item, value in values.items()
    ]


def build(bundle: DataBundle, as_of: date = AS_OF) -> CompanySnapshot:
    (snapshot,) = build_snapshots(bundle, as_of, NormalizationConfig())
    return snapshot


def bundle(
    *facts: FinancialFact, prices: tuple[float, date] | None = (50.0, date(2025, 6, 27))
) -> DataBundle:
    return DataBundle(
        issuers=(factories.issuer(),),
        equities=(factories.equity(),),
        financial_facts=facts,
        equity_prices=(factories.price(prices[1], prices[0]),) if prices else (),
    )


def test_fundamentals_are_measured_at_the_latest_published_period() -> None:
    snapshot = build(bundle(*statements(FY2023, revenue=900.0), *statements(FY2024)))
    assert snapshot.reference is not None
    assert snapshot.reference.period_end == FY2024
    assert snapshot.flow(FinancialItem.REVENUE).value == 1000.0
    assert snapshot.flow_prior_year(FinancialItem.REVENUE).value == 900.0
    assert snapshot.stock(FinancialItem.TOTAL_DEBT).value == 400.0
    assert snapshot.market_cap.value == 500.0  # 50 per share x 10 million shares


def test_statements_published_after_the_analysis_date_are_ignored() -> None:
    late = statements(FY2024, published_at=date(2025, 3, 15))
    snapshot = build(bundle(*statements(FY2023, revenue=900.0), *late), as_of=date(2025, 3, 1))
    assert snapshot.reference is not None
    assert snapshot.reference.period_end == FY2023
    assert snapshot.flow(FinancialItem.REVENUE).value == 900.0


def test_old_statements_are_flagged_as_stale() -> None:
    snapshot = build(bundle(*statements(FY2023)), as_of=date(2025, 6, 30))  # 547 days old
    revenue = snapshot.flow(FinancialItem.REVENUE)
    assert revenue.status is Status.STALE
    assert revenue.detail is not None
    assert "máximo 480" in revenue.detail
    assert snapshot.market_cap.status is Status.STALE  # the share count is stale too


def test_without_statements_everything_is_missing() -> None:
    snapshot = build(bundle())
    assert snapshot.reference is None
    assert snapshot.flow(FinancialItem.EBITDA).status is Status.MISSING
    assert snapshot.market_cap.status is Status.MISSING


def test_an_old_price_makes_market_values_stale() -> None:
    snapshot = build(bundle(*statements(FY2024), prices=(50.0, date(2025, 6, 1))))
    assert snapshot.price.status is Status.STALE
    assert snapshot.price_date == date(2025, 6, 1)
    assert snapshot.market_cap.status is Status.STALE


def test_market_cap_is_converted_into_the_reporting_currency() -> None:
    """Listed in euros, reporting in dollars (the 'other currency' edge case)."""
    data = DataBundle(
        issuers=(factories.issuer(currency="USD", country="NL"),),
        equities=(factories.equity(currency="EUR"),),
        financial_facts=tuple(statements(FY2024, currency="USD")),
        equity_prices=(factories.price(date(2025, 6, 27), 50.0, currency="EUR"),),
        fx_rates=(
            factories.fx("USD", date(2024, 3, 1), 1.08),
            factories.fx("USD", date(2024, 9, 2), 1.12),
            factories.fx("USD", date(2024, 12, 31), 1.04),
            factories.fx("USD", date(2025, 6, 27), 1.10),
        ),
    )
    snapshot = build(data)
    assert snapshot.market_cap.value == pytest.approx(550.0)  # 50 EUR x 10 x 1.10 USD/EUR
    assert snapshot.eur_spot_rate.value == 1.10
    assert snapshot.eur_average_rate.value == pytest.approx(1.08)  # (1.08 + 1.12 + 1.04) / 3
    assert snapshot.eur_closing_rate.value == 1.04


def test_bond_snapshot_uses_the_worst_current_rating_and_the_latest_quote() -> None:
    bond = factories.bond()
    data = DataBundle(
        issuers=(factories.issuer(),),
        equities=(factories.equity(),),
        bonds=(bond,),
        bond_quotes=(
            factories.quote(bond.isin, date(2025, 6, 20), 130.0),
            factories.quote(bond.isin, date(2025, 6, 27), 135.0),
        ),
        ratings=(
            factories.rating(bond.isin, "BBB+", date(2020, 1, 15), agency="AGENCY1"),
            factories.rating(bond.isin, "BBB-", date(2021, 1, 1), agency="AGENCY2"),
            factories.rating(bond.isin, "A-", date(2025, 8, 1), agency="AGENCY1"),  # future
        ),
    )
    (bond_snapshot,) = build(data).bonds
    assert bond_snapshot.rating is not None
    assert (bond_snapshot.rating.rating, bond_snapshot.rating.agency) == ("BBB-", "AGENCY2")
    assert bond_snapshot.spread.value == 135.0


def test_an_old_bond_quote_is_stale_and_matured_bonds_are_left_out() -> None:
    live = factories.bond(sequence=1)
    matured = factories.bond(sequence=2, issued=date(2015, 1, 1), maturity=date(2025, 1, 1))
    data = DataBundle(
        issuers=(factories.issuer(),),
        equities=(factories.equity(),),
        bonds=(live, matured),
        bond_quotes=(factories.quote(live.isin, date(2025, 6, 1), 140.0),),
    )
    (bond_snapshot,) = build(data).bonds
    assert bond_snapshot.bond.isin == live.isin
    assert bond_snapshot.spread.status is Status.STALE
