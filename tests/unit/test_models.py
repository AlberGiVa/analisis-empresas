from datetime import date

import pytest
from pydantic import ValidationError

from company_analysis.models import (
    DataBundle,
    FinancialFact,
    FinancialItem,
    FiscalPeriod,
    FxRate,
    Industry,
    Issuer,
    ItemKind,
    Sector,
)
from tests import factories


def test_issuer_industry_must_belong_to_its_sector() -> None:
    data = factories.issuer().model_dump() | {"sector": Sector.CONSUMER}
    with pytest.raises(ValidationError, match="no pertenece al sector"):
        Issuer.model_validate(data)


@pytest.mark.parametrize(
    ("industry", "expected"),
    [(Industry.BANKS, True), (Industry.INSURANCE, True), (Industry.SOFTWARE, False)],
)
def test_banks_and_insurers_are_financial_institutions(industry: Industry, expected: bool) -> None:
    assert factories.issuer(industry=industry).is_financial_institution is expected


def test_bond_must_mature_after_issue() -> None:
    with pytest.raises(ValidationError, match="vence antes de su emisión"):
        factories.bond(issued=date(2030, 1, 1), maturity=date(2025, 1, 1))


def test_fact_cannot_be_published_before_period_end() -> None:
    with pytest.raises(ValidationError, match="publicación es anterior"):
        factories.fact(FinancialItem.REVENUE, 100.0, published_at=date(2024, 12, 30))


def test_share_count_has_no_currency_and_amounts_require_one() -> None:
    shares = factories.fact(FinancialItem.SHARES_OUTSTANDING, 50.0)
    assert shares.currency is None
    with pytest.raises(ValidationError, match="divisa es obligatoria"):
        FinancialFact(
            issuer_id="TEST",
            fiscal_period=FiscalPeriod.FY,
            period_end=date(2024, 12, 31),
            item=FinancialItem.REVENUE,
            value=100.0,
            currency=None,
            published_at=date(2025, 2, 1),
        )


def test_item_catalogue_distinguishes_flows_and_stocks() -> None:
    assert FinancialItem.REVENUE.kind is ItemKind.FLOW
    assert FinancialItem.TOTAL_DEBT.kind is ItemKind.STOCK
    assert FiscalPeriod.H1.months == 6


def test_euro_has_no_exchange_rate() -> None:
    with pytest.raises(ValidationError, match="moneda base"):
        FxRate(currency="EUR", rate_date=date(2025, 1, 2), units_per_eur=1.0)


def test_bundle_rejects_duplicates_and_unknown_references() -> None:
    with pytest.raises(ValidationError) as error:
        DataBundle(
            issuers=(factories.issuer(), factories.issuer()),
            equities=(factories.equity("OTHER"),),
            equity_prices=(factories.price(date(2025, 1, 3), 10.0, issuer_id="NOPE"),),
        )
    message = str(error.value)
    assert "emisor duplicado" in message
    assert "emisor desconocido: OTHER" in message
    assert "acción desconocida" in message


def test_bundle_rejects_facts_in_a_currency_other_than_the_reporting_one() -> None:
    with pytest.raises(ValidationError, match="distinta de la de reporte"):
        DataBundle(
            issuers=(factories.issuer(currency="EUR"),),
            financial_facts=(factories.fact(FinancialItem.REVENUE, 100.0, currency="USD"),),
        )


def test_bundle_counts_records_per_collection() -> None:
    bundle = DataBundle(issuers=(factories.issuer(),), equities=(factories.equity(),))
    assert bundle.row_counts()["issuers"] == 1
    assert bundle.row_counts()["bonds"] == 0
