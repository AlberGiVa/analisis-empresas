"""Financial statement data in long format: one row per issuer, period and line item.

Monetary values are in millions of the issuer's reporting currency; shares in millions.
Expenses and outflows (interest expense, capital expenditure) are stored as positive amounts.
"""

from datetime import date
from enum import StrEnum
from typing import Self

from pydantic import FiniteFloat, model_validator

from company_analysis.models.base import DomainModel
from company_analysis.models.identifiers import CurrencyCode, IssuerId


class FiscalPeriod(StrEnum):
    """Reporting period. Interim periods are cumulative from the start of the fiscal year."""

    FY = "FY"
    Q1 = "Q1"
    H1 = "H1"
    NINE_MONTHS = "9M"

    @property
    def months(self) -> int:
        return _PERIOD_MONTHS[self]


_PERIOD_MONTHS = {
    FiscalPeriod.FY: 12,
    FiscalPeriod.Q1: 3,
    FiscalPeriod.H1: 6,
    FiscalPeriod.NINE_MONTHS: 9,
}


class ItemKind(StrEnum):
    FLOW = "flow"  # accumulates over the period (income statement, cash flow statement)
    STOCK = "stock"  # balance at the end of the period (balance sheet, share count)


class FinancialItem(StrEnum):
    """Closed catalogue of line items. Adding one is a deliberate, reviewed change."""

    REVENUE = "revenue"
    GROSS_PROFIT = "gross_profit"  # revenue minus cost of sales
    EBITDA = "ebitda"
    EBIT = "ebit"
    INTEREST_EXPENSE = "interest_expense"
    NET_INCOME = "net_income"  # attributable to the parent's shareholders
    OPERATING_CASH_FLOW = "operating_cash_flow"
    CAPITAL_EXPENDITURE = "capital_expenditure"
    TOTAL_DEBT = "total_debt"  # financial debt, including leases
    CASH = "cash"  # cash and cash equivalents
    TOTAL_EQUITY = "total_equity"  # including minority interests
    EQUITY_ATTRIBUTABLE = "equity_attributable"  # attributable to the parent's shareholders
    SHARES_OUTSTANDING = "shares_outstanding"  # millions of shares

    @property
    def kind(self) -> ItemKind:
        return _ITEM_INFO[self][0]

    @property
    def is_monetary(self) -> bool:
        return self is not FinancialItem.SHARES_OUTSTANDING

    @property
    def label(self) -> str:
        return _ITEM_INFO[self][1]


_ITEM_INFO = {
    FinancialItem.REVENUE: (ItemKind.FLOW, "Ventas"),
    FinancialItem.GROSS_PROFIT: (ItemKind.FLOW, "Beneficio bruto"),
    FinancialItem.EBITDA: (ItemKind.FLOW, "EBITDA"),
    FinancialItem.EBIT: (ItemKind.FLOW, "EBIT"),
    FinancialItem.INTEREST_EXPENSE: (ItemKind.FLOW, "Gastos financieros"),
    FinancialItem.NET_INCOME: (ItemKind.FLOW, "Beneficio neto atribuible"),
    FinancialItem.OPERATING_CASH_FLOW: (ItemKind.FLOW, "Flujo de caja operativo"),
    FinancialItem.CAPITAL_EXPENDITURE: (ItemKind.FLOW, "Inversiones (capex)"),
    FinancialItem.TOTAL_DEBT: (ItemKind.STOCK, "Deuda financiera"),
    FinancialItem.CASH: (ItemKind.STOCK, "Caja y equivalentes"),
    FinancialItem.TOTAL_EQUITY: (ItemKind.STOCK, "Patrimonio neto total"),
    FinancialItem.EQUITY_ATTRIBUTABLE: (ItemKind.STOCK, "Patrimonio neto atribuible"),
    FinancialItem.SHARES_OUTSTANDING: (ItemKind.STOCK, "Acciones en circulación (millones)"),
}


class FinancialFact(DomainModel):
    """One reported value, with the period it refers to and the date it became public."""

    issuer_id: IssuerId
    fiscal_period: FiscalPeriod
    period_end: date
    item: FinancialItem
    value: FiniteFloat
    currency: CurrencyCode | None
    published_at: date

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        if self.published_at < self.period_end:
            raise ValueError(
                f"{self.issuer_id} {self.item.value} {self.period_end}: "
                "la fecha de publicación es anterior al cierre del periodo"
            )
        if self.item.is_monetary != (self.currency is not None):
            raise ValueError(
                f"{self.issuer_id} {self.item.value}: la divisa es obligatoria en importes "
                "y no aplica a número de acciones"
            )
        return self
