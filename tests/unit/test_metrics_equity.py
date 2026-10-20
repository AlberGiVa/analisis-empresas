"""Equity metrics with hand-calculated values and every edge case."""

import pytest

from company_analysis.config import MetricsConfig
from company_analysis.figures import Figure, Status
from company_analysis.models import FinancialItem as Item
from tests.snapshots import compute, snapshot


def test_pe_ratio() -> None:
    result = compute("pe_ratio", snapshot(market_cap=1200.0, flows={Item.NET_INCOME: 100.0}))
    assert result.value == pytest.approx(12.0)
    assert result.inputs == {"Capitalización": 1200.0, "Beneficio neto atribuible LTM": 100.0}


@pytest.mark.parametrize(
    ("net_income", "status"),
    [(-50.0, Status.NOT_MEANINGFUL), (0.0, Status.DIVISION_BY_ZERO)],
)
def test_pe_ratio_without_profits(net_income: float, status: Status) -> None:
    result = compute("pe_ratio", snapshot(market_cap=1200.0, flows={Item.NET_INCOME: net_income}))
    assert result.status is status
    assert result.value is None


def test_pe_ratio_propagates_an_unavailable_price() -> None:
    stale = Figure.unavailable("Capitalización", Status.STALE, "cotización del 01/01/2025")
    result = compute("pe_ratio", snapshot(market_cap=stale, flows={Item.NET_INCOME: 100.0}))
    assert result.status is Status.STALE
    assert result.detail == "Capitalización: cotización del 01/01/2025"


def test_ev_to_ebitda() -> None:
    s = snapshot(
        market_cap=1000.0,
        stocks={Item.TOTAL_DEBT: 400.0, Item.CASH: 100.0},
        flows={Item.EBITDA: 150.0},
    )
    assert compute("ev_to_ebitda", s).value == pytest.approx(1300.0 / 150.0)  # 8.67x


def test_ev_to_ebitda_with_negative_ebitda_is_not_meaningful() -> None:
    s = snapshot(
        market_cap=1000.0,
        stocks={Item.TOTAL_DEBT: 400.0, Item.CASH: 100.0},
        flows={Item.EBITDA: -20.0},
    )
    result = compute("ev_to_ebitda", s)
    assert result.status is Status.NOT_MEANINGFUL
    assert result.detail == "EBITDA LTM es negativo (-20,0 M EUR)"


def test_ev_to_ebitda_with_negative_enterprise_value_is_not_meaningful() -> None:
    s = snapshot(
        market_cap=100.0,
        stocks={Item.TOTAL_DEBT: 0.0, Item.CASH: 300.0},
        flows={Item.EBITDA: 50.0},
    )
    assert compute("ev_to_ebitda", s).status is Status.NOT_MEANINGFUL


def test_fcf_yield_positive_and_negative() -> None:
    positive = snapshot(
        market_cap=2000.0,
        flows={Item.OPERATING_CASH_FLOW: 180.0, Item.CAPITAL_EXPENDITURE: 60.0},
    )
    assert compute("fcf_yield", positive).value == pytest.approx(0.06)  # 120 / 2000
    negative = snapshot(
        market_cap=2000.0,
        flows={Item.OPERATING_CASH_FLOW: 50.0, Item.CAPITAL_EXPENDITURE: 80.0},
    )
    assert compute("fcf_yield", negative).value == pytest.approx(-0.015)  # -30 / 2000


def test_fcf_yield_without_capex_is_missing() -> None:
    s = snapshot(market_cap=2000.0, flows={Item.OPERATING_CASH_FLOW: 180.0})
    result = compute("fcf_yield", s)
    assert result.status is Status.MISSING
    assert result.detail is not None
    assert "Inversiones (capex) LTM" in result.detail


def test_roe() -> None:
    s = snapshot(flows={Item.NET_INCOME: 90.0}, stocks={Item.EQUITY_ATTRIBUTABLE: 600.0})
    assert compute("roe", s).value == pytest.approx(0.15)
    losses = snapshot(flows={Item.NET_INCOME: -30.0}, stocks={Item.EQUITY_ATTRIBUTABLE: 600.0})
    assert compute("roe", losses).value == pytest.approx(-0.05)


def test_roe_with_negative_equity_is_not_meaningful() -> None:
    s = snapshot(flows={Item.NET_INCOME: 90.0}, stocks={Item.EQUITY_ATTRIBUTABLE: -100.0})
    assert compute("roe", s).status is Status.NOT_MEANINGFUL


def test_roic_uses_the_notional_tax_rate() -> None:
    s = snapshot(
        flows={Item.EBIT: 200.0},
        stocks={Item.TOTAL_EQUITY: 900.0, Item.TOTAL_DEBT: 500.0, Item.CASH: 200.0},
    )
    # 200 x (1 - 25 %) / (900 + 500 - 200) = 150 / 1200
    assert compute("roic", s).value == pytest.approx(0.125)
    # with a 30 % rate: 140 / 1200
    custom = compute("roic", s, MetricsConfig(notional_tax_rate=0.30))
    assert custom.value == pytest.approx(140.0 / 1200.0)
    assert custom.inputs["Tipo impositivo teórico"] == 0.30


@pytest.mark.parametrize(
    ("cash", "status"),
    [(1400.0, Status.DIVISION_BY_ZERO), (1600.0, Status.NOT_MEANINGFUL)],
)
def test_roic_without_positive_invested_capital(cash: float, status: Status) -> None:
    s = snapshot(
        flows={Item.EBIT: 200.0},
        stocks={Item.TOTAL_EQUITY: 900.0, Item.TOTAL_DEBT: 500.0, Item.CASH: cash},
    )
    assert compute("roic", s).status is status


def test_ebitda_margin() -> None:
    s = snapshot(flows={Item.EBITDA: 250.0, Item.REVENUE: 1000.0})
    assert compute("ebitda_margin", s).value == pytest.approx(0.25)
    negative = snapshot(flows={Item.EBITDA: -50.0, Item.REVENUE: 1000.0})
    assert compute("ebitda_margin", negative).value == pytest.approx(-0.05)
    no_sales = snapshot(flows={Item.EBITDA: 10.0, Item.REVENUE: 0.0})
    assert compute("ebitda_margin", no_sales).status is Status.DIVISION_BY_ZERO


def test_gross_margin() -> None:
    s = snapshot(flows={Item.GROSS_PROFIT: 400.0, Item.REVENUE: 1000.0})
    assert compute("gross_margin", s).value == pytest.approx(0.40)
    not_published = snapshot(flows={Item.REVENUE: 1000.0})
    assert compute("gross_margin", not_published).status is Status.MISSING
    no_sales = snapshot(flows={Item.GROSS_PROFIT: 10.0, Item.REVENUE: 0.0})
    assert compute("gross_margin", no_sales).status is Status.DIVISION_BY_ZERO


def test_fcf_conversion() -> None:
    flows = {Item.OPERATING_CASH_FLOW: 150.0, Item.CAPITAL_EXPENDITURE: 40.0}
    s = snapshot(flows={**flows, Item.NET_INCOME: 100.0})
    assert compute("fcf_conversion", s).value == pytest.approx(1.10)  # (150 - 40) / 100
    burning = snapshot(flows={**flows, Item.CAPITAL_EXPENDITURE: 200.0, Item.NET_INCOME: 100.0})
    assert compute("fcf_conversion", burning).value == pytest.approx(-0.50)
    losses = snapshot(flows={**flows, Item.NET_INCOME: -20.0})
    assert compute("fcf_conversion", losses).status is Status.NOT_MEANINGFUL


def test_revenue_growth() -> None:
    s = snapshot(flows={Item.REVENUE: 1100.0}, prior_flows={Item.REVENUE: 1000.0})
    assert compute("revenue_growth", s).value == pytest.approx(0.10)
    shrinking = snapshot(flows={Item.REVENUE: 900.0}, prior_flows={Item.REVENUE: 1000.0})
    assert compute("revenue_growth", shrinking).value == pytest.approx(-0.10)


@pytest.mark.parametrize(
    ("previous", "status"),
    [(None, Status.MISSING), (0.0, Status.DIVISION_BY_ZERO), (-10.0, Status.NOT_MEANINGFUL)],
)
def test_revenue_growth_without_a_valid_base(previous: float | None, status: Status) -> None:
    prior = {} if previous is None else {Item.REVENUE: previous}
    s = snapshot(flows={Item.REVENUE: 1100.0}, prior_flows=prior)
    assert compute("revenue_growth", s).status is status
