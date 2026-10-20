"""The study universe: which companies, how they are identified and how their debt is built.

The file is written and reviewed by hand (``estudio-real/universo.yaml``). It contains no market
data, only identifiers and mapping decisions, so it can live in the repository.
"""

from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from company_analysis.models import Equity, FinancialItem, Industry, Issuer, Sector
from company_analysis.models.identifiers import CountryCode, CurrencyCode, IssuerId
from company_analysis.providers.public.sec import DebtLine


class UniverseError(Exception):
    """The universe file is missing or invalid."""


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DebtLineEntry(_Model):
    line: str = Field(min_length=1)
    tags: list[str] = Field(min_length=1)
    required: bool = False


class CompanyEntry(_Model):
    id: IssuerId
    name: str = Field(min_length=1)
    cik: str = Field(pattern=r"^\d{10}$")
    ticker: str = Field(min_length=1)
    isin: str
    lei: str | None = None
    exchange: str = Field(pattern=r"^[A-Z0-9]{4}$")
    country: CountryCode
    sector: Sector
    industry: Industry
    currency: CurrencyCode
    fiscal_year_end_month: int = Field(ge=1, le=12)
    debt: list[DebtLineEntry] = Field(min_length=1)
    tags: dict[FinancialItem, list[str]] = Field(default_factory=dict)  # per-company overrides

    @model_validator(mode="after")
    def _one_required_debt_line(self) -> CompanyEntry:
        if not any(line.required for line in self.debt):
            raise ValueError(f"{self.id}: al menos una línea de deuda debe ser obligatoria")
        return self

    def issuer(self) -> Issuer:
        return Issuer(
            issuer_id=self.id,
            name=self.name,
            lei=self.lei,
            country=self.country,
            sector=self.sector,
            industry=self.industry,
            reporting_currency=self.currency,
            fiscal_year_end_month=self.fiscal_year_end_month,
        )

    def equity(self) -> Equity:
        return Equity(
            isin=self.isin,
            issuer_id=self.id,
            ticker=self.ticker,
            exchange=self.exchange,
            currency=self.currency,
        )

    def debt_lines(self) -> list[DebtLine]:
        return [DebtLine(e.line, tuple(e.tags), e.required) for e in self.debt]


class Universe(_Model):
    name: str
    description: str
    history_start: date  # first day of prices and exchange rates to download
    companies: list[CompanyEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_ids(self) -> Universe:
        ids = [company.id for company in self.companies]
        if len(ids) != len(set(ids)):
            raise ValueError("hay identificadores de empresa repetidos")
        return self

    @property
    def currencies(self) -> list[str]:
        return sorted({c.currency for c in self.companies} - {"EUR"})


def load_universe(path: Path) -> Universe:
    if not path.is_file():
        raise UniverseError(f"No se encuentra el universo del estudio: {path}")
    try:
        return Universe.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except (yaml.YAMLError, ValidationError) as error:
        raise UniverseError(f"El universo {path.name} no es válido:\n{error}") from error
