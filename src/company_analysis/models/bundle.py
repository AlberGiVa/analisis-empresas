"""A self-contained, validated set of data: what a provider delivers and what a run reads."""

from collections import Counter
from collections.abc import Hashable, Iterable
from typing import Self

from pydantic import model_validator

from company_analysis.models.base import DomainModel
from company_analysis.models.financials import FinancialFact
from company_analysis.models.market import BondQuote, EquityPrice, FxRate, RatingAction
from company_analysis.models.reference import Bond, Equity, Issuer

MAX_REPORTED_ERRORS = 20


def _duplicates(keys: Iterable[Hashable]) -> list[Hashable]:
    return [key for key, count in Counter(keys).items() if count > 1]


class DataBundle(DomainModel):
    """Reference data, financial statements and market data, checked for internal consistency."""

    issuers: tuple[Issuer, ...] = ()
    equities: tuple[Equity, ...] = ()
    bonds: tuple[Bond, ...] = ()
    financial_facts: tuple[FinancialFact, ...] = ()
    equity_prices: tuple[EquityPrice, ...] = ()
    bond_quotes: tuple[BondQuote, ...] = ()
    ratings: tuple[RatingAction, ...] = ()
    fx_rates: tuple[FxRate, ...] = ()

    @model_validator(mode="after")
    def _check_integrity(self) -> Self:
        errors = self._duplicate_key_errors() + self._reference_errors()
        if errors:
            shown = errors[:MAX_REPORTED_ERRORS]
            more = len(errors) - len(shown)
            suffix = f"\n- … y {more} más" if more else ""
            raise ValueError("Datos inconsistentes:\n- " + "\n- ".join(shown) + suffix)
        return self

    def _duplicate_key_errors(self) -> list[str]:
        checks: list[tuple[str, Iterable[Hashable]]] = [
            ("emisor", (i.issuer_id for i in self.issuers)),
            ("ISIN", [e.isin for e in self.equities] + [b.isin for b in self.bonds]),
            (
                "dato financiero",
                (
                    (f.issuer_id, f.fiscal_period, f.period_end, f.item, f.published_at)
                    for f in self.financial_facts
                ),
            ),
            ("cotización", ((p.isin, p.price_date) for p in self.equity_prices)),
            ("cotización de bono", ((q.isin, q.quote_date) for q in self.bond_quotes)),
            ("rating", ((r.isin, r.agency, r.rating_date) for r in self.ratings)),
            ("tipo de cambio", ((x.currency, x.rate_date) for x in self.fx_rates)),
        ]
        return [f"{name} duplicado: {key}" for name, keys in checks for key in _duplicates(keys)]

    def _reference_errors(self) -> list[str]:
        issuers = {issuer.issuer_id: issuer for issuer in self.issuers}
        equities = {equity.isin: equity for equity in self.equities}
        bond_isins = {bond.isin for bond in self.bonds}
        errors = [
            f"{kind} {isin} de un emisor desconocido: {issuer_id}"
            for kind, isin, issuer_id in [
                *(("La acción", e.isin, e.issuer_id) for e in self.equities),
                *(("El bono", b.isin, b.issuer_id) for b in self.bonds),
            ]
            if issuer_id not in issuers
        ]
        for fact in self.financial_facts:
            issuer = issuers.get(fact.issuer_id)
            if issuer is None:
                errors.append(f"Dato financiero de un emisor desconocido: {fact.issuer_id}")
            elif fact.currency is not None and fact.currency != issuer.reporting_currency:
                errors.append(
                    f"{fact.issuer_id} {fact.item.value} {fact.period_end}: divisa {fact.currency} "
                    f"distinta de la de reporte ({issuer.reporting_currency})"
                )
        for price in self.equity_prices:
            equity = equities.get(price.isin)
            if equity is None:
                errors.append(f"Cotización de una acción desconocida: {price.isin}")
            elif price.currency != equity.currency:
                errors.append(
                    f"Cotización de {price.isin} en {price.currency}, pero la acción cotiza "
                    f"en {equity.currency}"
                )
        errors.extend(
            f"{kind} de un bono desconocido: {isin}"
            for kind, isin in [
                *(("Cotización", q.isin) for q in self.bond_quotes),
                *(("Rating", r.isin) for r in self.ratings),
            ]
            if isin not in bond_isins
        )
        return errors

    def row_counts(self) -> dict[str, int]:
        """Number of records in each collection."""
        return {name: len(getattr(self, name)) for name in type(self).model_fields}
