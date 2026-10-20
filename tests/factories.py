"""Builders of small, valid domain objects for tests."""

from datetime import date

from company_analysis.models import (
    Bond,
    BondQuote,
    Equity,
    EquityPrice,
    FinancialFact,
    FinancialItem,
    FiscalPeriod,
    FxRate,
    Industry,
    Issuer,
    RatingAction,
    Seniority,
    SpreadType,
)
from company_analysis.providers.sample_generator import bond_isin, equity_isin, synthetic_lei


def issuer(
    issuer_id: str = "TEST",
    *,
    industry: Industry = Industry.CAPITAL_GOODS,
    currency: str = "EUR",
    country: str = "ES",
    fiscal_year_end_month: int = 12,
) -> Issuer:
    return Issuer(
        issuer_id=issuer_id,
        name=f"Empresa {issuer_id}",
        lei=synthetic_lei(issuer_id),
        country=country,
        sector=industry.sector,
        industry=industry,
        reporting_currency=currency,
        fiscal_year_end_month=fiscal_year_end_month,
    )


def equity(issuer_id: str = "TEST", *, currency: str = "EUR") -> Equity:
    return Equity(
        isin=equity_isin(issuer_id),
        issuer_id=issuer_id,
        ticker=issuer_id,
        exchange="XMAD",
        currency=currency,
    )


def bond(
    issuer_id: str = "TEST",
    sequence: int = 1,
    *,
    currency: str = "EUR",
    issued: date = date(2020, 1, 15),
    maturity: date = date(2030, 1, 15),
    seniority: Seniority = Seniority.SENIOR_UNSECURED,
) -> Bond:
    return Bond(
        isin=bond_isin(issuer_id, sequence),
        issuer_id=issuer_id,
        currency=currency,
        coupon_pct=4.0,
        coupon_frequency=1,
        issue_date=issued,
        maturity_date=maturity,
        seniority=seniority,
        amount_outstanding_mn=500.0,
    )


def fact(
    item: FinancialItem,
    value: float,
    *,
    issuer_id: str = "TEST",
    period_end: date = date(2024, 12, 31),
    published_at: date = date(2025, 2, 15),
    fiscal_period: FiscalPeriod = FiscalPeriod.FY,
    currency: str = "EUR",
) -> FinancialFact:
    return FinancialFact(
        issuer_id=issuer_id,
        fiscal_period=fiscal_period,
        period_end=period_end,
        item=item,
        value=value,
        currency=currency if item.is_monetary else None,
        published_at=published_at,
    )


def price(
    price_date: date, close: float, *, issuer_id: str = "TEST", currency: str = "EUR"
) -> EquityPrice:
    return EquityPrice(
        isin=equity_isin(issuer_id), price_date=price_date, close=close, currency=currency
    )


def quote(isin: str, quote_date: date, spread_bp: float, *, yield_pct: float = 4.0) -> BondQuote:
    return BondQuote(
        isin=isin,
        quote_date=quote_date,
        yield_pct=yield_pct,
        spread_bp=spread_bp,
        spread_type=SpreadType.Z_SPREAD,
    )


def rating(isin: str, code: str, rating_date: date, *, agency: str = "SAMPLE") -> RatingAction:
    return RatingAction(isin=isin, agency=agency, rating=code, rating_date=rating_date)


def fx(currency: str, rate_date: date, units_per_eur: float) -> FxRate:
    return FxRate(currency=currency, rate_date=rate_date, units_per_eur=units_per_eur)
