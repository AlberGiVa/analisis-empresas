"""Metrics on the sample data: every deliberate edge case shows up with the right status."""

from datetime import date

import pytest

from company_analysis.config import MetricsConfig, NormalizationConfig
from company_analysis.figures import Status
from company_analysis.metrics import MetricTable, compute_metrics
from company_analysis.models import DataBundle, FinancialItem, FiscalPeriod
from company_analysis.normalization import CompanySnapshot, build_snapshots, comparable_year
from company_analysis.providers import SampleProvider
from company_analysis.providers.sample_generator import DEMO_AS_OF_DATES, bond_isin
from company_analysis.settings import PROJECT_ROOT

PREVIOUS, CURRENT = DEMO_AS_OF_DATES


@pytest.fixture(scope="module")
def sample() -> DataBundle:
    return SampleProvider(PROJECT_ROOT / "data" / "sample").fetch()


@pytest.fixture(scope="module")
def snapshots(sample: DataBundle) -> dict[str, CompanySnapshot]:
    return {s.issuer_id: s for s in build_snapshots(sample, CURRENT, NormalizationConfig())}


@pytest.fixture(scope="module")
def table(snapshots: dict[str, CompanySnapshot]) -> MetricTable:
    return compute_metrics(list(snapshots.values()), MetricsConfig())


@pytest.mark.parametrize(
    ("issuer_id", "metric_id", "status"),
    [
        ("ORBE", "pe_ratio", Status.NOT_MEANINGFUL),  # negative EBITDA and losses
        ("ORBE", "ev_to_ebitda", Status.NOT_MEANINGFUL),
        ("ORBE", "net_debt_to_ebitda", Status.NOT_MEANINGFUL),
        ("ORBE", "interest_coverage", Status.OK),  # negative coverage is a valid value
        ("HELV", "interest_coverage", Status.DIVISION_BY_ZERO),  # no debt
        ("HELV", "debt_to_equity", Status.OK),
        ("HELV", "spread_vs_rating_bucket", Status.NOT_APPLICABLE),  # no bonds
        ("CORV", "fcf_yield", Status.MISSING),  # missing capex
        ("LUMB", "interest_coverage", Status.MISSING),  # missing interest expense
        ("SKRV", "pe_ratio", Status.STALE),  # no prices since March
        ("SKRV", "roe", Status.OK),  # fundamentals are not affected
        ("BVAL", "ev_to_ebitda", Status.NOT_APPLICABLE),
        ("WESB", "fcf_yield", Status.NOT_APPLICABLE),
        ("AUBR", "debt_to_equity", Status.NOT_APPLICABLE),
        ("BVAL", "pe_ratio", Status.OK),
        ("BVAL", "spread_vs_rating_bucket", Status.OK),
    ],
)
def test_edge_cases_of_the_sample(
    table: MetricTable, issuer_id: str, metric_id: str, status: Status
) -> None:
    result = table.result(issuer_id, metric_id)
    assert result.status is status, result.detail


def test_bonds_without_peers_or_rating(table: MetricTable) -> None:
    bonds = {row.entity_id: row.result for row in table.bond_rows("spread_vs_rating_bucket")}
    assert bonds[bond_isin("GRSH", 2)].status is Status.INSUFFICIENT_PEERS  # only AA- bond
    assert bonds[bond_isin("GRSH", 3)].status is Status.MISSING  # unrated
    assert bonds[bond_isin("ASHC", 1)].inputs["Mediana del tramo BB (pb)"] > 0  # downgraded


def test_market_cap_of_the_company_listed_in_euros_and_reporting_in_dollars(
    sample: DataBundle, snapshots: dict[str, CompanySnapshot]
) -> None:
    nexlio = snapshots["NEXL"]
    assert nexlio.equity is not None
    assert nexlio.equity.currency == "EUR"
    assert nexlio.price_date is not None
    usd_rate = next(
        rate.units_per_eur
        for rate in sample.fx_rates
        if rate.currency == "USD" and rate.rate_date == nexlio.price_date
    )
    shares = nexlio.stock(FinancialItem.SHARES_OUTSTANDING).number()
    expected = nexlio.price.number() * shares * usd_rate
    assert nexlio.market_cap.value == pytest.approx(expected)


def test_fiscal_year_ending_in_march_is_aligned(snapshots: dict[str, CompanySnapshot]) -> None:
    reference = snapshots["PELL"].reference
    assert reference is not None
    assert (reference.fiscal_period, reference.period_end) == (FiscalPeriod.FY, date(2026, 3, 31))
    assert comparable_year(reference.period_end) == 2025


def test_no_look_ahead_at_the_previous_demo_date(sample: DataBundle) -> None:
    previous = {s.issuer_id: s for s in build_snapshots(sample, PREVIOUS, NormalizationConfig())}
    for snapshot in previous.values():
        assert snapshot.reference is not None
        assert snapshot.reference.published_at <= PREVIOUS
    assert previous["VALD"].reference is not None
    assert previous["VALD"].reference.period_end == date(2024, 12, 31)
    assert previous["SKRV"].price.ok  # prices only stop in 2026
