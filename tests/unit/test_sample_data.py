"""The synthetic sample data: reproducible, unmistakably fictitious and with the edge cases."""

from collections import Counter
from pathlib import Path

import pytest

from company_analysis.models import DataBundle, FinancialItem, Industry, Sector
from company_analysis.models.ratings import rating_notch
from company_analysis.providers.sample import SAMPLE_FILES, SampleProvider, write_bundle_csv
from company_analysis.providers.sample_generator import DEMO_AS_OF_DATES, generate_sample_bundle
from company_analysis.settings import PROJECT_ROOT

SAMPLE_DIR = PROJECT_ROOT / "data" / "sample"


@pytest.fixture(scope="module")
def sample() -> DataBundle:
    return SampleProvider(SAMPLE_DIR).fetch()


def test_regenerating_produces_byte_identical_files(tmp_path: Path) -> None:
    write_bundle_csv(generate_sample_bundle(), tmp_path)
    for file_name, _model in SAMPLE_FILES.values():
        assert (tmp_path / file_name).read_bytes() == (SAMPLE_DIR / file_name).read_bytes(), (
            f"{file_name} no coincide: regenera con scripts/generate_sample_data.py"
        )


def test_every_identifier_is_synthetic(sample: DataBundle) -> None:
    """Guard against real market data in the repository: only synthetic identifiers allowed."""
    isins = [e.isin for e in sample.equities] + [b.isin for b in sample.bonds]
    assert all(isin.startswith("ZZ") for isin in isins)
    assert all(
        issuer.lei is not None and issuer.lei.startswith("ZZZZ") for issuer in sample.issuers
    )


def test_universe_has_twenty_companies_in_five_sectors(sample: DataBundle) -> None:
    assert len(sample.issuers) == 20
    assert {issuer.sector for issuer in sample.issuers} == set(Sector)
    industries = {issuer.industry for issuer in sample.issuers}
    assert {Industry.BANKS, Industry.INSURANCE} <= industries


def test_companies_have_one_to_three_bonds_except_the_one_without_debt(sample: DataBundle) -> None:
    bonds_per_issuer = Counter(bond.issuer_id for bond in sample.bonds)
    assert "HELV" not in bonds_per_issuer
    assert set(bonds_per_issuer.values()) <= {1, 2, 3}
    assert len(bonds_per_issuer) == 19


def _value(sample: DataBundle, issuer_id: str, item: FinancialItem, year: int) -> float | None:
    for fact in sample.financial_facts:
        if fact.issuer_id == issuer_id and fact.item is item and fact.period_end.year == year:
            return fact.value
    return None


def test_edge_case_negative_ebitda(sample: DataBundle) -> None:
    ebitda = _value(sample, "ORBE", FinancialItem.EBITDA, 2025)
    assert ebitda is not None
    assert ebitda < 0


def test_edge_case_company_without_debt(sample: DataBundle) -> None:
    assert _value(sample, "HELV", FinancialItem.TOTAL_DEBT, 2025) == 0
    assert _value(sample, "HELV", FinancialItem.INTEREST_EXPENSE, 2025) == 0


def test_edge_case_missing_items(sample: DataBundle) -> None:
    assert _value(sample, "CORV", FinancialItem.CAPITAL_EXPENDITURE, 2025) is None
    assert _value(sample, "CORV", FinancialItem.CAPITAL_EXPENDITURE, 2024) is not None
    assert _value(sample, "LUMB", FinancialItem.INTEREST_EXPENSE, 2025) is None
    rated = {rating.isin for rating in sample.ratings}
    assert len([bond for bond in sample.bonds if bond.isin not in rated]) == 1


def test_edge_case_reporting_currency_differs_from_listing(sample: DataBundle) -> None:
    nexlio = next(issuer for issuer in sample.issuers if issuer.issuer_id == "NEXL")
    listing = next(equity for equity in sample.equities if equity.issuer_id == "NEXL")
    assert (nexlio.reporting_currency, listing.currency) == ("USD", "EUR")


def test_edge_case_rating_downgrade_between_demo_dates(sample: DataBundle) -> None:
    previous, current = DEMO_AS_OF_DATES
    downgrades = [
        rating
        for rating in sample.ratings
        if rating.isin.startswith("ZZBASHC") and previous < rating.rating_date <= current
    ]
    assert downgrades
    assert all(rating.rating == "BB+" for rating in downgrades)


def test_edge_case_fiscal_year_ending_in_march(sample: DataBundle) -> None:
    pellingham = next(issuer for issuer in sample.issuers if issuer.issuer_id == "PELL")
    assert pellingham.fiscal_year_end_month == 3


def test_edge_case_rating_bucket_with_too_few_bonds(sample: DataBundle) -> None:
    aa_or_better = {rating.isin for rating in sample.ratings if rating_notch(rating.rating) <= 4}
    assert len(aa_or_better) == 1


def test_edge_case_stale_prices(sample: DataBundle) -> None:
    last_price = max(
        price.price_date for price in sample.equity_prices if price.isin.startswith("ZZESKRV")
    )
    assert (DEMO_AS_OF_DATES[1] - last_price).days > 30
