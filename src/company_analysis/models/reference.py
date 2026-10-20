"""Reference data: issuers (companies) and their instruments (shares and bonds)."""

from datetime import date
from typing import Self

from pydantic import Field, model_validator

from company_analysis.models.base import DomainModel
from company_analysis.models.classification import (
    FINANCIAL_INSTITUTIONS,
    Industry,
    Sector,
    Seniority,
)
from company_analysis.models.identifiers import CountryCode, CurrencyCode, Isin, IssuerId, Lei


class Issuer(DomainModel):
    """A company analysed both as a shareholder and as a creditor."""

    issuer_id: IssuerId
    name: str = Field(min_length=1)
    lei: Lei | None = None
    country: CountryCode
    sector: Sector
    industry: Industry
    reporting_currency: CurrencyCode
    fiscal_year_end_month: int = Field(ge=1, le=12)

    @model_validator(mode="after")
    def _industry_belongs_to_sector(self) -> Self:
        if self.industry.sector is not self.sector:
            raise ValueError(
                f"La industria {self.industry.value!r} no pertenece al sector {self.sector.value!r}"
            )
        return self

    @property
    def is_financial_institution(self) -> bool:
        """Banks and insurers, for which EBITDA, net debt and EV based metrics do not apply."""
        return self.industry in FINANCIAL_INSTITUTIONS


class Equity(DomainModel):
    """A listed share of an issuer."""

    isin: Isin
    issuer_id: IssuerId
    ticker: str = Field(min_length=1)
    exchange: str = Field(pattern=r"^[A-Z0-9]{4}$")  # ISO 10383 market identifier code (MIC)
    currency: CurrencyCode


class Bond(DomainModel):
    """A fixed-coupon corporate bond."""

    isin: Isin
    issuer_id: IssuerId
    currency: CurrencyCode
    coupon_pct: float = Field(ge=0, le=25)
    coupon_frequency: int = Field(ge=1, le=12)
    issue_date: date
    maturity_date: date
    seniority: Seniority
    amount_outstanding_mn: float = Field(gt=0)

    @model_validator(mode="after")
    def _matures_after_issue(self) -> Self:
        if self.maturity_date <= self.issue_date:
            raise ValueError(f"El bono {self.isin} vence antes de su emisión")
        return self
