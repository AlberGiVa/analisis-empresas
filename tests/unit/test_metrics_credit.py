"""Credit metrics with hand-calculated values and every edge case."""

from datetime import date

import pytest

from company_analysis.config import MetricsConfig
from company_analysis.figures import Figure, Status
from company_analysis.metrics import UniverseMetric, get_metric
from company_analysis.metrics.base import UniverseOutput
from company_analysis.models import FinancialItem as Item
from company_analysis.normalization import BondSnapshot, CompanySnapshot
from tests import factories
from tests.snapshots import compute, snapshot


def test_net_debt_to_ebitda() -> None:
    s = snapshot(stocks={Item.TOTAL_DEBT: 600.0, Item.CASH: 100.0}, flows={Item.EBITDA: 200.0})
    assert compute("net_debt_to_ebitda", s).value == pytest.approx(2.5)


def test_net_cash_gives_a_valid_negative_ratio() -> None:
    s = snapshot(stocks={Item.TOTAL_DEBT: 0.0, Item.CASH: 300.0}, flows={Item.EBITDA: 200.0})
    assert compute("net_debt_to_ebitda", s).value == pytest.approx(-1.5)


@pytest.mark.parametrize(
    ("ebitda", "status"),
    [(-10.0, Status.NOT_MEANINGFUL), (0.0, Status.DIVISION_BY_ZERO)],
)
def test_net_debt_to_ebitda_without_positive_ebitda(ebitda: float, status: Status) -> None:
    s = snapshot(stocks={Item.TOTAL_DEBT: 600.0, Item.CASH: 100.0}, flows={Item.EBITDA: ebitda})
    result = compute("net_debt_to_ebitda", s)
    assert result.status is status
    assert result.inputs["Deuda financiera"] == 600.0  # inputs are kept for the alerts


def test_interest_coverage() -> None:
    s = snapshot(flows={Item.EBITDA: 300.0, Item.INTEREST_EXPENSE: 40.0})
    assert compute("interest_coverage", s).value == pytest.approx(7.5)
    negative = snapshot(flows={Item.EBITDA: -30.0, Item.INTEREST_EXPENSE: 40.0})
    assert compute("interest_coverage", negative).value == pytest.approx(-0.75)


def test_interest_coverage_without_interest_is_a_division_by_zero() -> None:
    s = snapshot(flows={Item.EBITDA: 300.0, Item.INTEREST_EXPENSE: 0.0})
    result = compute("interest_coverage", s)
    assert result.status is Status.DIVISION_BY_ZERO
    assert result.detail == "Gastos financieros LTM es cero"


def test_debt_to_equity() -> None:
    s = snapshot(stocks={Item.TOTAL_DEBT: 500.0, Item.TOTAL_EQUITY: 1000.0})
    assert compute("debt_to_equity", s).value == pytest.approx(0.5)
    no_debt = snapshot(stocks={Item.TOTAL_DEBT: 0.0, Item.TOTAL_EQUITY: 1000.0})
    assert compute("debt_to_equity", no_debt).value == 0.0
    negative_equity = snapshot(stocks={Item.TOTAL_DEBT: 500.0, Item.TOTAL_EQUITY: -50.0})
    assert compute("debt_to_equity", negative_equity).status is Status.NOT_MEANINGFUL


# --- Spread against the rating bucket ------------------------------------------------------
QUOTE_DATE = date(2025, 6, 27)


def bond(issuer_id: str, sequence: int, spread: float | Figure, rating: str | None) -> BondSnapshot:
    instrument = factories.bond(issuer_id, sequence)
    if isinstance(spread, Figure):
        spread_figure, quote = spread, None
    else:
        spread_figure = Figure("Diferencial (pb)", spread)
        quote = factories.quote(instrument.isin, QUOTE_DATE, spread)
    action = (
        None if rating is None else factories.rating(instrument.isin, rating, date(2020, 1, 15))
    )
    return BondSnapshot(instrument, action, spread_figure, quote)


def company(issuer_id: str, *bonds: BondSnapshot) -> CompanySnapshot:
    return snapshot(issuer=factories.issuer(issuer_id), bonds=bonds)


STALE = Figure.unavailable("Diferencial (pb)", Status.STALE, "cotización antigua")
UNIVERSE = [
    company("AAAA", bond("AAAA", 1, 100.0, "BBB"), bond("AAAA", 2, 150.0, "BBB")),
    company("BBBB", bond("BBBB", 1, 120.0, "BBB-"), bond("BBBB", 2, 80.0, "A")),
    company("CCCC", bond("CCCC", 1, 200.0, "BBB+"), bond("CCCC", 2, 90.0, None)),
    company("DDDD"),
    company("EEEE", bond("EEEE", 1, STALE, "A-")),
    company("FFFF", bond("FFFF", 1, 70.0, "A+")),
]


def spreads(config: MetricsConfig | None = None) -> UniverseOutput:
    definition = get_metric("spread_vs_rating_bucket")
    assert isinstance(definition, UniverseMetric)
    return definition.compute(UNIVERSE, config or MetricsConfig())


def isin(issuer_id: str, sequence: int) -> str:
    return factories.bond(issuer_id, sequence).isin


def test_each_bond_is_compared_with_the_median_of_its_bucket() -> None:
    bonds = spreads().bonds
    # BBB bucket (BBB+, BBB, BBB-): 100, 120, 150, 200 -> median 135
    expected = {("AAAA", 1): -35.0, ("AAAA", 2): 15.0, ("BBBB", 1): -15.0, ("CCCC", 1): 65.0}
    for (issuer_id, sequence), excess in expected.items():
        result = bonds[isin(issuer_id, sequence)][1]
        assert result.value == pytest.approx(excess)
        assert result.inputs["Mediana del tramo BBB (pb)"] == pytest.approx(135.0)


def test_bonds_without_enough_peers_unrated_or_stale_have_no_value() -> None:
    bonds = spreads().bonds
    # the A bucket only has two bonds with a valid spread (the stale one does not count)
    assert bonds[isin("BBBB", 2)][1].status is Status.INSUFFICIENT_PEERS
    assert bonds[isin("FFFF", 1)][1].status is Status.INSUFFICIENT_PEERS
    assert bonds[isin("CCCC", 2)][1].status is Status.MISSING
    assert bonds[isin("EEEE", 1)][1].status is Status.STALE


def test_company_value_is_the_median_of_its_bonds() -> None:
    issuers = spreads().issuers
    assert issuers["AAAA"].value == pytest.approx(-10.0)  # median of -35 and +15
    assert issuers["BBBB"].value == pytest.approx(-15.0)  # its A bond has no peers
    assert issuers["BBBB"].detail == "mediana de 1 de 2 bonos"
    assert issuers["CCCC"].value == pytest.approx(65.0)
    assert issuers["DDDD"].status is Status.NOT_APPLICABLE
    assert issuers["EEEE"].status is Status.STALE
    assert issuers["FFFF"].status is Status.INSUFFICIENT_PEERS


def test_the_minimum_bucket_size_is_configurable() -> None:
    bonds = spreads(MetricsConfig(min_bonds_per_rating_bucket=2)).bonds
    # A bucket: 80 and 70 -> median 75
    assert bonds[isin("BBBB", 2)][1].value == pytest.approx(5.0)
    assert bonds[isin("FFFF", 1)][1].value == pytest.approx(-5.0)


def test_rating_buckets_cover_the_whole_scale() -> None:
    config = MetricsConfig()
    assert config.bucket_for("AA-").name == "AAA-AA"
    assert config.bucket_for("BBB-").name == "BBB"
    assert config.bucket_for("Ba1").name == "BB"
    assert config.bucket_for("D").name == "CCC o inferior"
