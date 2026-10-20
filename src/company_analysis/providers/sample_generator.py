"""Deterministic generator of the synthetic sample data stored in ``data/sample``.

Twenty fictitious listed companies in five sectors, three fiscal years (2023-2025), weekly share
prices and bond quotes, daily exchange rates and a rating history. Identifiers are synthetic and
cannot be confused with real ones: ISINs start with ``ZZ`` and LEIs with ``ZZZZ`` (codes not
assigned to any country or registration agency), with valid check digits.

The data deliberately include edge cases, documented in ``data/sample/README.md``.

The same seed always produces byte-identical files; a test checks it. A NumPy upgrade could change
the random stream: if that test fails after an upgrade, regenerate and commit the files.
"""

import calendar
import math
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np

from company_analysis.models import (
    Bond,
    BondQuote,
    DataBundle,
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
from company_analysis.models.identifiers import isin_check_digit, lei_check_digits
from company_analysis.models.ratings import rating_notch

SEED = 20261020
FISCAL_YEARS = (2023, 2024, 2025)
MARKET_START = date(2023, 1, 6)  # first weekly close (a Friday)
MARKET_END = date(2026, 6, 30)
FX_START = date(2022, 12, 1)
RATING_AGENCY = "SAMPLE"  # fictitious agency that uses S&P/Fitch notation

# Analysis dates of the demo: before and after the FY2025 results and the rating downgrade.
DEMO_AS_OF_DATES = (date(2025, 12, 31), date(2026, 6, 30))

MINORITY_SHARE = 0.03
WORKING_CAPITAL_PCT = 0.10
BUYBACK_RATE = 0.01

# --- Deliberate edge cases -------------------------------------------------------------------
MISSING_ITEMS: dict[tuple[str, int], frozenset[FinancialItem]] = {
    ("CORV", 2025): frozenset({FinancialItem.CAPITAL_EXPENDITURE}),
    ("LUMB", 2025): frozenset({FinancialItem.INTEREST_EXPENSE}),
}
PRICE_STOP = {"SKRV": date(2026, 3, 27)}  # no prices afterwards: stale at the second demo date
RATING_CHANGES = {
    "VERD": (date(2024, 5, 20), "A"),  # upgrade from A-
    "ASHC": (date(2026, 3, 12), "BB+"),  # downgrade from BBB- (falls to high yield)
}
SPREAD_STRESS = {"ASHC": (date(2025, 9, 1), date(2026, 3, 12), 60.0)}  # widening before downgrade

# --- Market model ----------------------------------------------------------------------------
_BASE_SPREAD_BP = {
    4: 45.0, 5: 60.0, 6: 70.0, 7: 80.0, 8: 100.0, 9: 120.0, 10: 150.0,
    11: 210.0, 12: 260.0, 13: 320.0, 14: 380.0, 15: 450.0, 16: 520.0,
}  # fmt: skip
_SENIORITY_SPREAD_BP = {
    Seniority.SENIOR_SECURED: -10.0,
    Seniority.SENIOR_UNSECURED: 0.0,
    Seniority.SENIOR_NON_PREFERRED: 25.0,
    Seniority.SUBORDINATED: 90.0,
    Seniority.JUNIOR_SUBORDINATED: 200.0,
}
_CURRENCY_SPREAD_BP = {"EUR": 0.0, "USD": 10.0, "GBP": 15.0}
_BENCHMARK = {"EUR": (2.2, 0.06), "USD": (3.9, 0.03), "GBP": (4.0, 0.05)}  # level %, slope %/year
_FX_START = {"USD": 1.07, "GBP": 0.87, "CHF": 0.98, "SEK": 11.20}  # units per euro
_FX_DAILY_VOL = {"USD": 0.0045, "GBP": 0.0035, "CHF": 0.0030, "SEK": 0.0045}

_EXCHANGES = {
    "ES": "XMAD", "DE": "XETR", "FR": "XPAR", "IT": "XMIL", "NL": "XAMS",
    "GB": "XLON", "CH": "XSWX", "SE": "XSTO", "US": "XNYS",
}  # fmt: skip


@dataclass(frozen=True)
class BondSpec:
    currency: str
    seniority: Seniority
    rating: str  # initial rating; it also drives the simulated spread
    issued: date
    maturity: date
    amount_mn: float
    rated: bool = True  # False: the bond has no published rating


@dataclass(frozen=True)
class CompanySpec:
    issuer_id: str
    name: str
    country: str
    industry: Industry
    reporting_currency: str
    listing_currency: str
    revenue: float  # first fiscal year, millions of reporting currency
    growth: tuple[float, float]  # revenue growth in the second and third fiscal years
    target_pe: float  # sets the initial market capitalisation
    price: float  # first weekly close, in the listing currency
    drift: float  # annual price drift
    volatility: float  # annual price volatility
    roe: float  # sets the book equity of the first fiscal year
    payout: float
    bonds: tuple[BondSpec, ...] = ()
    fiscal_year_end_month: int = 12
    # Corporates
    ebitda_margin: tuple[float, float, float] = (0.0, 0.0, 0.0)
    da_pct: float = 0.0
    leverage: tuple[float, float, float] = (0.0, 0.0, 0.0)  # target net debt / EBITDA
    cash_pct: float = 0.0
    interest_rate: float = 0.0
    tax_rate: float = 0.25
    capex_pct: float = 0.0
    # Banks and insurers report a reduced set of items: net income as a share of revenue.
    net_margin: tuple[float, float, float] | None = None
    # Loss-making company: debt, book equity and valuation cannot come from the ratios above.
    fixed_debt: float | None = None
    equity_start: float | None = None
    market_cap_to_revenue: float | None = None


def _bond(
    currency: str,
    seniority: Seniority,
    rating: str,
    issued: str,
    maturity: str,
    amount_mn: float,
    *,
    rated: bool = True,
) -> BondSpec:
    return BondSpec(
        currency,
        seniority,
        rating,
        date.fromisoformat(issued),
        date.fromisoformat(maturity),
        amount_mn,
        rated,
    )


_SU = Seniority.SENIOR_UNSECURED

COMPANIES: tuple[CompanySpec, ...] = (
    # --- Industrials ---
    CompanySpec(
        "VALD", "Valdoria Maquinaria, S.A.", "ES", Industry.CAPITAL_GOODS, "EUR", "EUR",
        revenue=4200, growth=(0.06, 0.05), target_pe=14, price=28.0, drift=0.08,
        volatility=0.22, roe=0.13, payout=0.45, ebitda_margin=(0.14, 0.145, 0.15),
        da_pct=0.04, leverage=(1.8, 1.7, 1.6), cash_pct=0.08, interest_rate=0.040,
        capex_pct=0.04,
        bonds=(
            _bond("EUR", _SU, "BBB", "2019-05-14", "2028-05-14", 500),
            _bond("EUR", _SU, "BBB", "2022-10-03", "2032-10-03", 600),
        ),
    ),
    CompanySpec(
        "RHFD", "Rheinfeld Antriebe AG", "DE", Industry.CAPITAL_GOODS, "EUR", "EUR",
        revenue=9800, growth=(0.03, 0.04), target_pe=16, price=95.0, drift=0.07,
        volatility=0.20, roe=0.14, payout=0.40, ebitda_margin=(0.16, 0.16, 0.165),
        da_pct=0.05, leverage=(1.2, 1.1, 1.0), cash_pct=0.10, interest_rate=0.035,
        tax_rate=0.29, capex_pct=0.05,
        bonds=(
            _bond("EUR", _SU, "A-", "2020-02-11", "2029-02-11", 750),
            _bond("EUR", _SU, "A-", "2023-03-08", "2034-03-08", 750),
        ),
    ),
    CompanySpec(
        "CORV", "Corvalis Transports SA", "FR", Industry.TRANSPORTATION, "EUR", "EUR",
        revenue=6500, growth=(0.04, 0.02), target_pe=12, price=42.0, drift=0.04,
        volatility=0.24, roe=0.11, payout=0.50, ebitda_margin=(0.11, 0.115, 0.11),
        da_pct=0.06, leverage=(2.2, 2.0, 2.1), cash_pct=0.07, interest_rate=0.042,
        capex_pct=0.06,
        bonds=(
            _bond("EUR", _SU, "BBB+", "2020-06-17", "2027-06-17", 500),
            _bond("EUR", _SU, "BBB+", "2021-11-22", "2031-11-22", 600),
        ),
    ),
    CompanySpec(
        "SKRV", "Skarvik Logistik AB", "SE", Industry.TRANSPORTATION, "SEK", "SEK",
        revenue=38000, growth=(0.05, 0.03), target_pe=13, price=160.0, drift=0.05,
        volatility=0.26, roe=0.12, payout=0.50, ebitda_margin=(0.12, 0.12, 0.125),
        da_pct=0.06, leverage=(2.4, 2.3, 2.5), cash_pct=0.06, interest_rate=0.045,
        tax_rate=0.206, capex_pct=0.07,
        bonds=(_bond("EUR", _SU, "BBB-", "2023-04-19", "2030-04-19", 500),),
    ),
    CompanySpec(
        "TALM", "Talmont Aerospace Corp.", "US", Industry.CAPITAL_GOODS, "USD", "USD",
        revenue=15500, growth=(0.09, 0.08), target_pe=22, price=120.0, drift=0.12,
        volatility=0.25, roe=0.18, payout=0.30, ebitda_margin=(0.18, 0.185, 0.19),
        da_pct=0.045, leverage=(1.0, 0.9, 0.8), cash_pct=0.09, interest_rate=0.048,
        tax_rate=0.21, capex_pct=0.04,
        bonds=(
            _bond("USD", _SU, "A", "2018-09-12", "2028-09-12", 1000),
            _bond("USD", _SU, "A", "2021-03-02", "2033-03-02", 1000),
            _bond("USD", _SU, "A", "2023-05-24", "2035-05-24", 750),
        ),
    ),
    CompanySpec(
        "ASHC", "Ashcombe Infrastructure plc", "GB", Industry.CONSTRUCTION, "GBP", "GBP",
        revenue=3100, growth=(0.02, -0.03), target_pe=11, price=4.20, drift=-0.10,
        volatility=0.30, roe=0.10, payout=0.50, ebitda_margin=(0.13, 0.115, 0.095),
        da_pct=0.04, leverage=(2.8, 3.3, 4.1), cash_pct=0.06, interest_rate=0.055,
        capex_pct=0.03,
        bonds=(
            _bond("GBP", _SU, "BBB-", "2019-07-09", "2029-07-09", 400),
            _bond("GBP", _SU, "BBB-", "2022-01-25", "2033-01-25", 350),
        ),
    ),
    # --- Consumer ---
    CompanySpec(
        "MRND", "Merindad Alimentación, S.A.", "ES", Industry.FOOD_BEVERAGE, "EUR", "EUR",
        revenue=5300, growth=(0.04, 0.04), target_pe=17, price=22.0, drift=0.06,
        volatility=0.18, roe=0.15, payout=0.55, ebitda_margin=(0.12, 0.125, 0.125),
        da_pct=0.035, leverage=(2.0, 1.9, 1.8), cash_pct=0.06, interest_rate=0.040,
        capex_pct=0.035,
        bonds=(
            _bond("EUR", _SU, "BBB", "2020-09-15", "2028-09-15", 400),
            _bond("EUR", _SU, "BBB", "2023-01-31", "2031-01-31", 500),
        ),
    ),
    CompanySpec(
        "LUMB", "Lumbria Moda S.p.A.", "IT", Industry.RETAIL, "EUR", "EUR",
        revenue=2400, growth=(0.01, -0.02), target_pe=10, price=7.50, drift=-0.05,
        volatility=0.32, roe=0.09, payout=0.30, ebitda_margin=(0.13, 0.12, 0.11),
        da_pct=0.05, leverage=(3.2, 3.4, 3.9), cash_pct=0.05, interest_rate=0.065,
        tax_rate=0.24, capex_pct=0.04,
        bonds=(
            _bond("EUR", _SU, "BB", "2021-04-13", "2029-04-13", 500),
            _bond("EUR", Seniority.SUBORDINATED, "B+", "2021-04-13", "2031-04-13", 300),
        ),
    ),
    CompanySpec(
        "HOLL", "Hollow Creek Brands Inc.", "US", Industry.CONSUMER_PRODUCTS, "USD", "USD",
        revenue=11200, growth=(0.05, 0.06), target_pe=21, price=64.0, drift=0.09,
        volatility=0.19, roe=0.24, payout=0.50, ebitda_margin=(0.21, 0.215, 0.22),
        da_pct=0.03, leverage=(2.0, 1.8, 1.7), cash_pct=0.05, interest_rate=0.046,
        tax_rate=0.22, capex_pct=0.03,
        bonds=(
            _bond("USD", _SU, "A-", "2020-08-04", "2030-08-04", 800),
            _bond("USD", _SU, "A-", "2024-02-13", "2034-02-13", 700),
        ),
    ),
    CompanySpec(
        "PELL", "Pellingham & Rowe plc", "GB", Industry.RETAIL, "GBP", "GBP",
        revenue=4800, growth=(0.03, 0.02), target_pe=12, price=3.10, drift=0.03,
        volatility=0.24, roe=0.13, payout=0.50, ebitda_margin=(0.09, 0.095, 0.09),
        da_pct=0.03, leverage=(1.9, 1.8, 2.0), cash_pct=0.05, interest_rate=0.052,
        capex_pct=0.035, fiscal_year_end_month=3,
        bonds=(_bond("GBP", _SU, "BBB-", "2020-10-06", "2030-10-06", 350),),
    ),
    CompanySpec(
        "VERD", "Verdalia Foods N.V.", "NL", Industry.FOOD_BEVERAGE, "EUR", "EUR",
        revenue=7700, growth=(0.05, 0.05), target_pe=19, price=51.0, drift=0.08,
        volatility=0.18, roe=0.17, payout=0.55, ebitda_margin=(0.16, 0.165, 0.17),
        da_pct=0.04, leverage=(1.6, 1.5, 1.4), cash_pct=0.07, interest_rate=0.036,
        tax_rate=0.258, capex_pct=0.045,
        bonds=(
            _bond("EUR", _SU, "A-", "2019-03-26", "2029-03-26", 600),
            _bond("EUR", _SU, "A-", "2022-09-20", "2033-09-20", 600),
        ),
    ),
    # --- Technology ---
    CompanySpec(
        "KELV", "Kelvane Software Inc.", "US", Industry.SOFTWARE, "USD", "USD",
        revenue=3600, growth=(0.15, 0.13), target_pe=26, price=48.0, drift=0.10,
        volatility=0.35, roe=0.16, payout=0.0, ebitda_margin=(0.24, 0.25, 0.26),
        da_pct=0.06, leverage=(2.8, 2.4, 2.0), cash_pct=0.12, interest_rate=0.060,
        tax_rate=0.21, capex_pct=0.03,
        bonds=(
            _bond("USD", _SU, "BB+", "2021-06-08", "2029-06-08", 750),
            _bond("USD", _SU, "BB+", "2023-09-12", "2032-09-12", 500),
        ),
    ),
    CompanySpec(
        "NEXL", "Nexlio Semiconductors N.V.", "NL", Industry.SEMICONDUCTORS, "USD", "EUR",
        revenue=8900, growth=(0.11, 0.12), target_pe=25, price=74.0, drift=0.14,
        volatility=0.30, roe=0.21, payout=0.25, ebitda_margin=(0.31, 0.32, 0.33),
        da_pct=0.07, leverage=(0.6, 0.5, 0.4), cash_pct=0.15, interest_rate=0.044,
        tax_rate=0.22, capex_pct=0.09,
        bonds=(
            _bond("USD", _SU, "BBB", "2021-10-19", "2029-10-19", 800),
            _bond("USD", _SU, "BBB", "2024-03-05", "2034-03-05", 600),
        ),
    ),
    CompanySpec(
        "ORBE", "Orbelia Digital, S.A.", "ES", Industry.IT_SERVICES, "EUR", "EUR",
        revenue=950, growth=(0.04, -0.06), target_pe=0, price=3.20, drift=-0.10,
        volatility=0.35, roe=0.0, payout=0.0, ebitda_margin=(0.05, -0.04, -0.09),
        da_pct=0.07, cash_pct=0.13, interest_rate=0.080, capex_pct=0.07,
        fixed_debt=600, equity_start=700, market_cap_to_revenue=0.8,
        bonds=(
            _bond("EUR", _SU, "B", "2021-02-23", "2028-02-23", 300),
            _bond("EUR", _SU, "B", "2022-06-28", "2030-06-28", 250),
        ),
    ),
    CompanySpec(
        "HELV", "Helvantis Data AG", "CH", Industry.SOFTWARE, "CHF", "CHF",
        revenue=2100, growth=(0.10, 0.09), target_pe=28, price=85.0, drift=0.10,
        volatility=0.28, roe=0.20, payout=0.35, ebitda_margin=(0.28, 0.29, 0.30),
        da_pct=0.05, cash_pct=0.35, tax_rate=0.14, capex_pct=0.03, fixed_debt=0,
    ),
    # --- Utilities ---
    CompanySpec(
        "VTIB", "Valtiberina Energia S.p.A.", "IT", Industry.ELECTRIC_UTILITIES, "EUR", "EUR",
        revenue=12500, growth=(-0.04, 0.02), target_pe=13, price=6.80, drift=0.05,
        volatility=0.17, roe=0.10, payout=0.65, ebitda_margin=(0.24, 0.27, 0.28),
        da_pct=0.10, leverage=(3.0, 2.9, 2.8), cash_pct=0.05, interest_rate=0.038,
        tax_rate=0.24, capex_pct=0.14,
        bonds=(
            _bond("EUR", _SU, "BBB+", "2017-11-14", "2027-11-14", 1000),
            _bond("EUR", _SU, "BBB+", "2021-05-18", "2031-05-18", 900),
            _bond("EUR", _SU, "BBB+", "2023-10-10", "2036-10-10", 800),
        ),
    ),
    CompanySpec(
        "GRSH", "Gresham Power & Light Co.", "US", Industry.ELECTRIC_UTILITIES, "USD", "USD",
        revenue=8100, growth=(0.03, 0.04), target_pe=17, price=58.0, drift=0.04,
        volatility=0.16, roe=0.095, payout=0.65, ebitda_margin=(0.37, 0.38, 0.38),
        da_pct=0.13, leverage=(4.6, 4.5, 4.4), cash_pct=0.03, interest_rate=0.045,
        tax_rate=0.21, capex_pct=0.22,
        bonds=(
            _bond("USD", _SU, "A", "2021-01-26", "2031-01-26", 900),
            _bond("USD", Seniority.SENIOR_SECURED, "AA-", "2020-04-21", "2035-04-21", 700),
            _bond("USD", _SU, "A", "2023-08-15", "2029-08-15", 400, rated=False),
        ),
    ),
    # --- Financials ---
    CompanySpec(
        "BVAL", "Banco Valdemora, S.A.", "ES", Industry.BANKS, "EUR", "EUR",
        revenue=9600, growth=(0.08, 0.03), target_pe=8, price=6.10, drift=0.12,
        volatility=0.25, roe=0.12, payout=0.50, net_margin=(0.28, 0.30, 0.31),
        bonds=(
            _bond("EUR", _SU, "A-", "2022-03-15", "2028-03-15", 1000),
            _bond("EUR", Seniority.SENIOR_NON_PREFERRED, "BBB", "2023-02-07", "2030-02-07", 750),
            _bond("EUR", Seniority.SUBORDINATED, "BB+", "2021-09-21", "2033-09-21", 500),
        ),
    ),
    CompanySpec(
        "WESB", "Weserland Bank AG", "DE", Industry.BANKS, "EUR", "EUR",
        revenue=4100, growth=(0.05, 0.01), target_pe=9, price=14.0, drift=0.08,
        volatility=0.27, roe=0.08, payout=0.40, net_margin=(0.20, 0.22, 0.21),
        bonds=(
            _bond("EUR", _SU, "BBB+", "2021-07-06", "2029-07-06", 750),
            _bond("EUR", Seniority.SUBORDINATED, "BBB-", "2022-05-10", "2032-05-10", 400),
        ),
    ),
    CompanySpec(
        "AUBR", "Aubrac Assurances SA", "FR", Industry.INSURANCE, "EUR", "EUR",
        revenue=21000, growth=(0.04, 0.05), target_pe=11, price=31.0, drift=0.09,
        volatility=0.18, roe=0.13, payout=0.55, net_margin=(0.065, 0.07, 0.072),
        bonds=(
            _bond("EUR", _SU, "A", "2020-11-24", "2030-11-24", 500),
            _bond("EUR", Seniority.SUBORDINATED, "BBB+", "2024-01-16", "2034-01-16", 750),
        ),
    ),
)  # fmt: skip


# --- Identifiers -----------------------------------------------------------------------------
def synthetic_isin(prefix: str, code: str) -> str:
    """ISIN starting with ``ZZ`` (not an assigned country code) and a valid check digit."""
    body = ("ZZ" + prefix + code).ljust(11, "0")[:11]
    return body + str(isin_check_digit(body))


def synthetic_lei(issuer_id: str) -> str:
    """LEI starting with ``ZZZZ`` (not an assigned registration agency) and valid check digits."""
    body = ("ZZZZ00" + issuer_id).ljust(18, "0")[:18]
    return body + lei_check_digits(body)


def equity_isin(issuer_id: str) -> str:
    return synthetic_isin("E", issuer_id)


def bond_isin(issuer_id: str, sequence: int) -> str:
    return synthetic_isin("B", f"{issuer_id[:4]}{sequence:04d}")


# --- Calendars -------------------------------------------------------------------------------
def _weekly_dates(start: date, end: date) -> Iterator[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=7)


def _business_days(start: date, end: date) -> Iterator[date]:
    current = start
    while current <= end:
        if current.weekday() < 5:
            yield current
        current += timedelta(days=1)


def fiscal_period_end(year: int, fiscal_year_end_month: int) -> date:
    """Closing date of the fiscal year that compares with calendar year ``year``.

    A fiscal year belongs to the calendar year in which most of its months fall: one ending in
    March 2026 compares with calendar 2025.
    """
    end_year = year if fiscal_year_end_month >= 6 else year + 1
    return date(
        end_year, fiscal_year_end_month, calendar.monthrange(end_year, fiscal_year_end_month)[1]
    )


# --- Financial statements --------------------------------------------------------------------
def _statements(spec: CompanySpec, rng: np.random.Generator) -> list[dict[FinancialItem, float]]:
    """Values of each fiscal year (before rounding and before removing missing items)."""
    revenues = [spec.revenue]
    for growth in spec.growth:
        revenues.append(revenues[-1] * (1 + growth))
    if spec.net_margin is not None:
        return _financial_institution_statements(spec, revenues)

    years: list[dict[FinancialItem, float]] = []
    equity = spec.equity_start
    previous_revenue = spec.revenue / 1.04
    for index, revenue in enumerate(revenues):
        ebitda = revenue * spec.ebitda_margin[index]
        ebit = ebitda - revenue * spec.da_pct
        cash = revenue * spec.cash_pct
        if spec.fixed_debt is not None:
            debt = spec.fixed_debt
        else:
            debt = max(spec.leverage[index] * ebitda + cash, 0.0)
        interest = debt * spec.interest_rate
        pretax = ebit - interest
        tax = max(pretax, 0.0) * spec.tax_rate
        net_income = (pretax - tax) * (1 - MINORITY_SHARE)
        if equity is None:
            equity = net_income / spec.roe
        else:
            equity += net_income * (1 - spec.payout) if net_income > 0 else net_income
        working_capital_change = (revenue - previous_revenue) * WORKING_CAPITAL_PCT
        noise = float(rng.normal(0.0, 0.03)) * abs(ebitda)
        years.append(
            {
                FinancialItem.REVENUE: revenue,
                FinancialItem.EBITDA: ebitda,
                FinancialItem.EBIT: ebit,
                FinancialItem.INTEREST_EXPENSE: interest,
                FinancialItem.NET_INCOME: net_income,
                FinancialItem.OPERATING_CASH_FLOW: ebitda
                - tax
                - interest
                - working_capital_change
                + noise,
                FinancialItem.CAPITAL_EXPENDITURE: revenue * spec.capex_pct,
                FinancialItem.TOTAL_DEBT: debt,
                FinancialItem.CASH: cash,
                FinancialItem.TOTAL_EQUITY: equity * (1 + MINORITY_SHARE),
                FinancialItem.EQUITY_ATTRIBUTABLE: equity,
            }
        )
        previous_revenue = revenue
    return years


def _financial_institution_statements(
    spec: CompanySpec, revenues: list[float]
) -> list[dict[FinancialItem, float]]:
    """Banks and insurers report revenue, net income and equity only."""
    assert spec.net_margin is not None
    years: list[dict[FinancialItem, float]] = []
    equity: float | None = None
    for index, revenue in enumerate(revenues):
        net_income = revenue * spec.net_margin[index]
        equity = (
            net_income / spec.roe if equity is None else equity + net_income * (1 - spec.payout)
        )
        years.append(
            {
                FinancialItem.REVENUE: revenue,
                FinancialItem.NET_INCOME: net_income,
                FinancialItem.TOTAL_EQUITY: equity * (1 + MINORITY_SHARE),
                FinancialItem.EQUITY_ATTRIBUTABLE: equity,
            }
        )
    return years


def _initial_shares(spec: CompanySpec, first_year: dict[FinancialItem, float]) -> float:
    """Millions of shares that give the target valuation at the first weekly close."""
    net_income = first_year[FinancialItem.NET_INCOME]
    if spec.market_cap_to_revenue is not None:
        market_cap = spec.market_cap_to_revenue * spec.revenue
    else:
        market_cap = spec.target_pe * net_income
    price = spec.price
    if spec.listing_currency != spec.reporting_currency:
        price *= _fx_start(spec.reporting_currency) / _fx_start(spec.listing_currency)
    return market_cap / price


def _fx_start(currency: str) -> float:
    return 1.0 if currency == "EUR" else _FX_START[currency]


def _financial_facts(spec: CompanySpec, rng: np.random.Generator) -> list[FinancialFact]:
    """Facts of the three fiscal years, without the deliberately missing items."""
    statements = _statements(spec, rng)
    shares = _initial_shares(spec, statements[0])
    facts: list[FinancialFact] = []
    for index, (year, values) in enumerate(zip(FISCAL_YEARS, statements, strict=True)):
        period_end = fiscal_period_end(year, spec.fiscal_year_end_month)
        lag = int(
            rng.integers(62, 75) if spec.fiscal_year_end_month != 12 else rng.integers(38, 86)
        )
        published_at = period_end + timedelta(days=lag)
        year_values = {
            **values,
            FinancialItem.SHARES_OUTSTANDING: shares * (1 - BUYBACK_RATE) ** index,
        }
        missing = MISSING_ITEMS.get((spec.issuer_id, year), frozenset())
        facts.extend(
            FinancialFact(
                issuer_id=spec.issuer_id,
                fiscal_period=FiscalPeriod.FY,
                period_end=period_end,
                item=item,
                value=round(value, 2 if item is FinancialItem.SHARES_OUTSTANDING else 1) + 0.0,
                currency=spec.reporting_currency if item.is_monetary else None,
                published_at=published_at,
            )
            for item, value in year_values.items()
            if item not in missing
        )
    return facts


# --- Market data -----------------------------------------------------------------------------
def _equity_prices(
    spec: CompanySpec, isin: str, fridays: list[date], rng: np.random.Generator
) -> list[EquityPrice]:
    weekly_vol = spec.volatility / math.sqrt(52)
    weekly_drift = spec.drift / 52 - 0.5 * weekly_vol**2
    stop = PRICE_STOP.get(spec.issuer_id, MARKET_END)
    price = spec.price
    prices = []
    for friday in fridays:
        if friday <= stop:
            prices.append(
                EquityPrice(
                    isin=isin,
                    price_date=friday,
                    close=round(price, 2),
                    currency=spec.listing_currency,
                )
            )
        price *= math.exp(weekly_drift + weekly_vol * float(rng.standard_normal()))
    return prices


def _autoregressive(
    dates: list[date], rng: np.random.Generator, *, persistence: float, shock: float
) -> dict[date, float]:
    """Mean-reverting series around zero, one value per date."""
    value = 0.0
    series = {}
    for day in dates:
        value = persistence * value + shock * float(rng.standard_normal())
        series[day] = value
    return series


def _rating_on(spec: CompanySpec, bond: BondSpec, day: date) -> str:
    change = RATING_CHANGES.get(spec.issuer_id)
    if change is not None and day >= change[0]:
        return change[1]
    return bond.rating


def _stress_bp(issuer_id: str, day: date) -> float:
    """Issuer-specific widening that anticipates a downgrade."""
    stress = SPREAD_STRESS.get(issuer_id)
    if stress is None or day < stress[0]:
        return 0.0
    start, peak_date, peak = stress
    if day >= peak_date:
        return peak * 2 / 3
    return peak * (day - start).days / (peak_date - start).days


def _coupon_pct(bond: BondSpec) -> float:
    level, slope = _BENCHMARK[bond.currency]
    tenor = (bond.maturity - bond.issued).days / 365.25
    spread = (
        _BASE_SPREAD_BP[rating_notch(bond.rating)]
        + _SENIORITY_SPREAD_BP[bond.seniority]
        + _CURRENCY_SPREAD_BP[bond.currency]
    )
    raw = level + slope * min(tenor, 10.0) + spread / 100
    return round(raw * 8) / 8


def _bond_quotes(
    spec: CompanySpec,
    bond: BondSpec,
    isin: str,
    fridays: list[date],
    market: dict[date, float],
    benchmarks: dict[str, dict[date, float]],
    issuer_premium: float,
    rng: np.random.Generator,
) -> list[BondQuote]:
    level, slope = _BENCHMARK[bond.currency]
    quotes = []
    for friday in fridays:
        if not bond.issued <= friday <= bond.maturity:
            continue
        years = (bond.maturity - friday).days / 365.25
        base = (
            _BASE_SPREAD_BP[rating_notch(_rating_on(spec, bond, friday))]
            + _SENIORITY_SPREAD_BP[bond.seniority]
            + _CURRENCY_SPREAD_BP[bond.currency]
            + 4.0 * (years - 5.0)
            + issuer_premium
            + _stress_bp(spec.issuer_id, friday)
        )
        spread = max(base * (1 + market[friday]) + float(rng.normal(0.0, 2.0)), 5.0)
        bond_yield = level + benchmarks[bond.currency][friday] + slope * min(years, 10.0)
        quotes.append(
            BondQuote(
                isin=isin,
                quote_date=friday,
                yield_pct=round(bond_yield + spread / 100, 3),
                spread_bp=round(spread, 1),
                spread_type=SpreadType.Z_SPREAD,
            )
        )
    return quotes


def _ratings(spec: CompanySpec, bond: BondSpec, isin: str) -> list[RatingAction]:
    if not bond.rated:
        return []
    actions = [
        RatingAction(isin=isin, agency=RATING_AGENCY, rating=bond.rating, rating_date=bond.issued)
    ]
    change = RATING_CHANGES.get(spec.issuer_id)
    if change is not None and bond.issued < change[0] <= MARKET_END:
        actions.append(
            RatingAction(isin=isin, agency=RATING_AGENCY, rating=change[1], rating_date=change[0])
        )
    return actions


def _fx_rates(rng: np.random.Generator) -> list[FxRate]:
    days = list(_business_days(FX_START, MARKET_END))
    rates = []
    for currency, start in _FX_START.items():
        anchor = math.log(start)
        level = anchor
        for day in days:
            rates.append(
                FxRate(currency=currency, rate_date=day, units_per_eur=round(math.exp(level), 4))
            )
            level += 0.002 * (anchor - level) + _FX_DAILY_VOL[currency] * float(
                rng.standard_normal()
            )
    return rates


# --- Assembly --------------------------------------------------------------------------------
def generate_sample_bundle(seed: int = SEED) -> DataBundle:
    """Build the whole synthetic dataset. The same seed always gives the same bundle."""
    fridays = list(_weekly_dates(MARKET_START, MARKET_END))
    market = _autoregressive(
        fridays, np.random.default_rng([seed, 1]), persistence=0.95, shock=0.02
    )
    benchmarks = {
        currency: _autoregressive(
            fridays, np.random.default_rng([seed, 2, index]), persistence=0.98, shock=0.05
        )
        for index, currency in enumerate(_BENCHMARK)
    }
    issuers: list[Issuer] = []
    equities: list[Equity] = []
    bonds: list[Bond] = []
    facts: list[FinancialFact] = []
    prices: list[EquityPrice] = []
    quotes: list[BondQuote] = []
    ratings: list[RatingAction] = []
    for index, spec in enumerate(COMPANIES, start=1):
        rng = np.random.default_rng([seed, 100, index])
        issuers.append(
            Issuer(
                issuer_id=spec.issuer_id,
                name=spec.name,
                lei=synthetic_lei(spec.issuer_id),
                country=spec.country,
                sector=spec.industry.sector,
                industry=spec.industry,
                reporting_currency=spec.reporting_currency,
                fiscal_year_end_month=spec.fiscal_year_end_month,
            )
        )
        facts.extend(_financial_facts(spec, rng))
        isin = equity_isin(spec.issuer_id)
        equities.append(
            Equity(
                isin=isin,
                issuer_id=spec.issuer_id,
                ticker=spec.issuer_id,
                exchange=_EXCHANGES[spec.country],
                currency=spec.listing_currency,
            )
        )
        prices.extend(_equity_prices(spec, isin, fridays, rng))
        issuer_premium = float(rng.normal(0.0, 12.0))
        for sequence, bond in enumerate(spec.bonds, start=1):
            isin = bond_isin(spec.issuer_id, sequence)
            bonds.append(
                Bond(
                    isin=isin,
                    issuer_id=spec.issuer_id,
                    currency=bond.currency,
                    coupon_pct=_coupon_pct(bond),
                    coupon_frequency=1 if bond.currency == "EUR" else 2,
                    issue_date=bond.issued,
                    maturity_date=bond.maturity,
                    seniority=bond.seniority,
                    amount_outstanding_mn=bond.amount_mn,
                )
            )
            quotes.extend(
                _bond_quotes(spec, bond, isin, fridays, market, benchmarks, issuer_premium, rng)
            )
            ratings.extend(_ratings(spec, bond, isin))
    return DataBundle(
        issuers=tuple(issuers),
        equities=tuple(equities),
        bonds=tuple(bonds),
        financial_facts=tuple(facts),
        equity_prices=tuple(prices),
        bond_quotes=tuple(quotes),
        ratings=tuple(ratings),
        fx_rates=tuple(_fx_rates(np.random.default_rng([seed, 3]))),
    )
