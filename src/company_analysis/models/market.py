"""Market data: share prices, bond quotes, rating actions and exchange rates."""

from datetime import date
from enum import StrEnum
from typing import Self

from pydantic import Field, FiniteFloat, model_validator

from company_analysis.models.base import DomainModel
from company_analysis.models.identifiers import BASE_CURRENCY, CurrencyCode, Isin
from company_analysis.models.ratings import RatingCode


class EquityPrice(DomainModel):
    """Closing price of a share, in its quotation currency."""

    isin: Isin
    price_date: date
    close: float = Field(gt=0)
    currency: CurrencyCode


class SpreadType(StrEnum):
    Z_SPREAD = "z_spread"
    G_SPREAD = "g_spread"
    OAS = "oas"


class BondQuote(DomainModel):
    """Market yield and spread of a bond on a given date."""

    isin: Isin
    quote_date: date
    yield_pct: FiniteFloat
    spread_bp: FiniteFloat
    spread_type: SpreadType


class RatingAction(DomainModel):
    """A bond's rating from one agency, effective (and public) from ``rating_date``."""

    isin: Isin
    agency: str = Field(min_length=1)
    rating: RatingCode
    rating_date: date


class FxRate(DomainModel):
    """Exchange rate quoted as units of ``currency`` per one euro (ECB convention)."""

    currency: CurrencyCode
    rate_date: date
    units_per_eur: float = Field(gt=0)

    @model_validator(mode="after")
    def _not_the_base_currency(self) -> Self:
        if self.currency == BASE_CURRENCY:
            raise ValueError("El euro es la moneda base: no lleva tipo de cambio")
        return self
