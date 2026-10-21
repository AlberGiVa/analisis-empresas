"""Synthetic responses shaped like SEC EDGAR, filings.xbrl.org, Nasdaq, Yahoo Finance and the ECB.

All the data are invented.

The fictitious company reports on calendar years and has every awkward case seen in real
filings: comparatives repeated in later reports, a restated figure, a lone quarter in the
half-year report, a twelve-month disclosure that is not a fiscal year, a tag that changes over
time, a share count only on the cover page, a debt line absent from some balance sheets and an
impaired quarter.
"""

import json
from collections.abc import Callable, Iterable
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from company_analysis.providers.sample_generator import equity_isin, synthetic_lei

MN = 1_000_000

# Quarterly revenue by fiscal (= calendar) year; 2026 has two quarters reported.
REVENUE = {2023: [240, 245, 250, 255], 2024: [250, 255, 260, 265], 2025: [260, 270, 280, 290]}
REVENUE_2026 = [280, 300]
IMPAIRED_QUARTER_EBIT = -100.0  # second quarter of 2026: an impairment

QUARTER_ENDS = ((3, 31), (6, 30), (9, 30), (12, 31))


def _quarter_end(year: int, quarter: int) -> date:
    month, day = QUARTER_ENDS[quarter - 1]
    return date(year, month, day)


def _quarterly(year: int) -> list[float]:
    return [float(v) for v in (REVENUE_2026 if year == 2026 else REVENUE[year])]


def _ebit(year: int, quarter: int) -> float:
    if (year, quarter) == (2026, 2):
        return IMPAIRED_QUARTER_EBIT
    return 0.2 * _quarterly(year)[quarter - 1]


FLOWS: dict[str, Callable[[int, int], float]] = {  # tag -> value of one quarter
    "Revenues": lambda y, q: _quarterly(y)[q - 1],
    "OperatingIncomeLoss": _ebit,
    "DepreciationAndAmortization": lambda y, q: 0.05 * _quarterly(y)[q - 1],
    "NetIncomeLoss": lambda y, q: 0.12 * _quarterly(y)[q - 1],
    "NetCashProvidedByUsedInOperatingActivities": lambda y, q: 0.18 * _quarterly(y)[q - 1],
    "PaymentsToAcquirePropertyPlantAndEquipment": lambda y, q: 0.06 * _quarterly(y)[q - 1],
    "InterestExpenseNonoperating": lambda y, q: 0.02 * _quarterly(y)[q - 1],
}


# (accession, form, filed, fiscal year, quarters covered)
FILINGS = (
    ("0001-24-1", "10-K", date(2024, 2, 14), 2023, 4),
    ("0001-25-1", "10-Q", date(2025, 4, 30), 2025, 1),
    ("0001-25-0", "10-K", date(2025, 2, 14), 2024, 4),
    ("0001-25-2", "10-Q", date(2025, 7, 31), 2025, 2),
    ("0001-25-3", "10-Q", date(2025, 10, 31), 2025, 3),
    ("0001-26-0", "10-K", date(2026, 2, 13), 2025, 4),
    ("0001-26-1", "10-Q", date(2026, 4, 30), 2026, 1),
    ("0001-26-2", "10-Q", date(2026, 7, 31), 2026, 2),
)


def _entry(
    start: date | None, end: date, value: float, filed: date, accn: str, form: str
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "end": end.isoformat(),
        "val": value,
        "accn": accn,
        "form": form,
        "filed": filed.isoformat(),
    }
    if start is not None:
        entry["start"] = start.isoformat()
    return entry


def _cumulative(tag: str, year: int, quarters: int) -> float:
    return sum(FLOWS[tag](year, q) for q in range(1, quarters + 1))


def companyfacts(scale: float = 1.0) -> dict[str, Any]:
    gaap: dict[str, list[dict[str, Any]]] = {tag: [] for tag in FLOWS}
    for tag in ("InterestExpense", "CashAndCashEquivalentsAtCarryingValue", "StockholdersEquity",
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
                "MinorityInterest", "LongTermDebtNoncurrent", "ShortTermBorrowings"):  # fmt: skip
        gaap[tag] = []
    cover: list[dict[str, Any]] = []
    for accn, form, filed, year, quarters in FILINGS:
        for fiscal_year in (year, year - 1):  # current period and the prior-year comparative
            start, end = date(fiscal_year, 1, 1), _quarter_end(fiscal_year, quarters)
            if fiscal_year == 2022:
                continue
            for tag in FLOWS:
                value = _cumulative(tag, fiscal_year, quarters)
                if (
                    tag == "OperatingIncomeLoss"
                    and fiscal_year == 2024
                    and quarters == 4
                    and filed.year == 2026
                ):
                    value -= 6.0  # FY 2024 restated in the 2025 annual report
                gaap[tag].append(_entry(start, end, scale * value * MN, filed, accn, form))
            if filed.year < 2026:  # the gross interest tag stops being used in 2026
                value = _cumulative("InterestExpenseNonoperating", fiscal_year, quarters)
                gaap["InterestExpense"].append(
                    _entry(start, end, scale * value * MN, filed, accn, form)
                )
            if quarters == 2 and fiscal_year == year:  # a lone quarter: never a fiscal period
                lone = FLOWS["Revenues"](fiscal_year, 2)
                gaap["Revenues"].append(
                    _entry(date(fiscal_year, 4, 1), end, scale * lone * MN, filed, accn, form)
                )
            for tag, value in (
                ("CashAndCashEquivalentsAtCarryingValue", 100.0 + fiscal_year - 2020),
                ("StockholdersEquity", 500.0),
                ("StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", 510.0),
                ("MinorityInterest", 10.0),
                ("LongTermDebtNoncurrent", 400.0),
            ):
                gaap[tag].append(_entry(None, end, scale * value * MN, filed, accn, form))
            if quarters == 4:  # short-term borrowings only appear on annual balance sheets
                gaap["ShortTermBorrowings"].append(
                    _entry(None, end, scale * 50.0 * MN, filed, accn, form)
                )
        cover.append(_entry(None, filed - timedelta(days=5), scale * 100.0 * MN, filed, accn, form))
    # A twelve-month disclosure that is not a fiscal year (October to September).
    gaap["Revenues"].append(
        _entry(
            date(2024, 10, 1),
            date(2025, 9, 30),
            scale * 1080 * MN,
            date(2026, 2, 13),
            "0001-26-0",
            "10-K",
        )
    )
    usd = {tag: {"units": {"USD": entries}} for tag, entries in gaap.items()}
    return {
        "cik": 1,
        "entityName": "ZETA FOODS INC",
        "facts": {
            "us-gaap": usd,
            "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": cover}}},
        },
    }


def submissions() -> dict[str, Any]:
    """The filing register already lists a report whose figures are not in the structured data."""
    filings = [("10-Q", "2026-09-30", "2026-10-15", "0001-26-3")] + [
        (form, _quarter_end(year, quarters).isoformat(), filed.isoformat(), accn)
        for accn, form, filed, year, quarters in sorted(FILINGS, key=lambda f: f[2], reverse=True)
    ]
    return {
        "filings": {
            "recent": {
                "form": [f[0] for f in filings],
                "reportDate": [f[1] for f in filings],
                "filingDate": [f[2] for f in filings],
                "accessionNumber": [f[3] for f in filings],
            }
        }
    }


def trading_days(start: date, end: date) -> list[date]:
    return [
        start + timedelta(days=i)
        for i in range((end - start).days + 1)
        if (start + timedelta(days=i)).weekday() < 5
    ]


def nasdaq(days: Iterable[date], close: float) -> dict[str, Any]:
    rows = [
        {"date": f"{d:%m/%d/%Y}", "close": f"${close + i * 0.01:,.2f}"} for i, d in enumerate(days)
    ]
    return {"data": {"tradesTable": {"rows": list(reversed(rows))}}}


def yahoo(days: Iterable[date], close: float) -> dict[str, Any]:
    days = list(days)
    stamps = [
        int((d - date(1970, 1, 1)).days * 86_400 + 13.5 * 3600) for d in days
    ]  # 09:30 New York
    closes = [round(close + i * 0.01, 2) for i in range(len(days))]
    return {
        "chart": {
            "result": [
                {
                    "meta": {"gmtoffset": -14400, "exchangeName": "NYQ"},
                    "timestamp": stamps,
                    "indicators": {"quote": [{"close": closes}]},
                }
            ]
        }
    }


def ecb_csv(days: Iterable[date], rate: float) -> str:
    lines = ["KEY,FREQ,CURRENCY,TIME_PERIOD,OBS_VALUE"]
    lines += [f"EXR.D.USD.EUR.SP00.A,D,USD,{d.isoformat()},{rate}" for d in days]
    return "\n".join(lines) + "\n"


COMPANIES = (
    ("ZZAA", "Zeta Foods Inc.", "0000000001", 1.0),
    ("ZZBB", "Beta Home Corp.", "0000000002", 1.6),
)

# --- A European company: annual reports in ESEF (xBRL-JSON of filings.xbrl.org) ------------------
EU_ID, EU_NAME = "ZZEU", "Europa Alimentación, S.A."
EU_LEI = synthetic_lei(EU_ID)
IFRS_2024 = "https://xbrl.ifrs.org/taxonomy/2024-03-27/ifrs-full"
# Figures of each fiscal (= calendar) year, in millions of euros.
EU_CONCEPTS = (
    "Revenue",
    "ProfitLossFromOperatingActivities",
    "DepreciationAndAmortisationExpense",
    "FinanceCosts",
    "ProfitLossAttributableToOwnersOfParent",
    "CashFlowsFromUsedInOperatingActivities",
    "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
    "CashAndCashEquivalents",
    "Equity",
    "EquityAttributableToOwnersOfParent",
    "CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings",
    "NoncurrentPortionOfNoncurrentBorrowings",
)
EU_YEARS: dict[int, dict[str, float]] = {
    year: dict(zip(EU_CONCEPTS, values, strict=True))
    for year, values in {
        2023: (950, 110, 38, 14, 72, 130, 48, 80, 560, 540, 35, 320),
        2024: (1000, 120, 40, 15, 80, 140, 50, 90, 600, 580, 30, 300),
        2025: (1100, 130, 45, 16, 88, 150, 55, 100, 650, 630, 25, 280),
    }.items()
}
EU_BALANCES = {
    "CashAndCashEquivalents",
    "Equity",
    "EquityAttributableToOwnersOfParent",
    "CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings",
    "NoncurrentPortionOfNoncurrentBorrowings",
}
# (fiscal year, fxo_id, published by the source, added to filings.xbrl.org)
EU_FILINGS = (
    (2024, f"{EU_LEI}-2024-12-31-ESEF-ES-0", None, "2025-05-08 11:09:48"),
    (2024, f"{EU_LEI}-2024-12-31-ESEF-ES-1", "2025-02-27 00:00:00", "2026-10-20 15:46:16"),
    (2025, f"{EU_LEI}-2025-12-31-ESEF-ES-0", "2026-02-26 00:00:00", "2026-03-02 09:00:00"),
)


DESCRIPTION = "DescriptionOfNatureOfEntitysOperationsAndPrincipalActivities"


def esef_index() -> dict[str, Any]:
    """The company's filings in filings.xbrl.org: the 2024 report is listed twice."""
    return {
        "data": [
            {
                "type": "filing",
                "id": str(number),
                "attributes": {
                    "period_end": f"{year}-12-31",
                    "fxo_id": fxo_id,
                    "published": published,
                    "date_added": added,
                    "json_url": f"/{EU_LEI}/{year}-12-31/ESEF/ES/{fxo_id[-1]}/report.json",
                },
            }
            for number, (year, fxo_id, published, added) in enumerate(EU_FILINGS, start=1)
        ]
    }


def _esef_fact(prefix: str, concept: str, year: int, value: float, **extra: str) -> dict[str, Any]:
    if concept in EU_BALANCES:
        period = f"{year + 1}-01-01T00:00:00"  # the end of 31 December
    else:
        period = f"{year}-01-01T00:00:00/{year + 1}-01-01T00:00:00"
    dimensions = {
        "concept": f"{prefix}:{concept}",
        "entity": f"scheme:{extra.pop('entity', EU_LEI)}",
        "period": period,
        "unit": extra.pop("unit", "iso4217:EUR"),
        **extra,
    }
    return {"value": str(value * MN), "decimals": -6, "dimensions": dimensions}


def esef_report(year: int) -> dict[str, Any]:
    """The annual report of ``year`` (with the previous year as comparative), as xBRL-JSON.

    The 2024 report names the IFRS taxonomy with another prefix. The 2025 one also has a segment
    breakdown, a text, a ratio and a fact of another entity, none of which may be read.
    """
    prefix = "ifrs" if year == 2024 else "ifrs-full"
    facts = [
        _esef_fact(prefix, concept, fiscal, value)
        for fiscal in (year, year - 1)
        for concept, value in EU_YEARS[fiscal].items()
    ]
    if year == 2025:
        facts += [
            _esef_fact(prefix, "Revenue", 2025, 600, **{"ifrs-full:SegmentsAxis": "eu:FoodMember"}),
            _esef_fact(prefix, "Revenue", 2025, 5, entity="ZZZZ00OTHER000000000"),
            _esef_fact(prefix, "BasicEarningsPerShare", 2025, 1, unit="iso4217:EUR/xbrli:shares"),
            {
                "value": "Fabrica alimentos.",
                "dimensions": {
                    "concept": f"{prefix}:{DESCRIPTION}",
                    "entity": f"scheme:{EU_LEI}",
                    "period": "2025-01-01T00:00:00/2026-01-01T00:00:00",
                    "language": "es",
                },
            },
        ]
    return {
        "documentInfo": {
            "documentType": "https://xbrl.org/2021/xbrl-json",
            "namespaces": {prefix: IFRS_2024, "eu": "http://www.example.invalid/2025"},
        },
        "facts": {f"f-{number}": fact for number, fact in enumerate(facts, start=1)},
    }


PRICE_DAYS = trading_days(date(2026, 6, 1), date(2026, 8, 14))


def write_universe(root: Path, *, european: bool = False) -> Path:
    """The universe of the tests; ``european`` adds a company with ESEF annual reports."""
    lines = [
        'name: "Universo de prueba"',
        'description: "Empresas inventadas para las pruebas."',
        "history_start: 2026-06-01",
        "companies:",
    ]
    for identifier, name, cik, _ in COMPANIES:
        lines += [
            f"  - id: {identifier}",
            f"    name: {name}",
            f'    cik: "{cik}"',
            f"    ticker: {identifier}",
            f"    isin: {equity_isin(identifier)}",
            "    exchange: XNYS",
            "    country: US",
            "    sector: consumer",
            "    industry: food_beverage",
            "    currency: USD",
            "    fiscal_year_end_month: 12",
            "    debt:",
            '      - {line: "Préstamos a corto plazo", tags: [ShortTermBorrowings]}',
            '      - {line: "Deuda a largo plazo", tags: [LongTermDebtNoncurrent], required: true}',
        ]
    if european:
        lines += [
            f"  - id: {EU_ID}",
            f"    name: {EU_NAME}",
            "    source: esef",
            f"    ticker: {EU_ID}",
            f"    isin: {equity_isin(EU_ID)}",
            f"    lei: {EU_LEI}",
            "    exchange: XMAD",
            "    country: ES",
            "    sector: consumer",
            "    industry: food_beverage",
            "    currency: EUR",
            "    fiscal_year_end_month: 12",
            "    debt:",
            '      - {line: "Deuda financiera a corto plazo", '
            "tags: [CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings]}",
            '      - {line: "Deuda financiera a largo plazo", '
            "tags: [NoncurrentPortionOfNoncurrentBorrowings], required: true}",
        ]
    path = root / "universo.yaml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_snapshot(folder: Path, *, prices: bool = True, european: bool = False) -> Path:
    """A downloaded snapshot (with its manifest) as the downloader would leave it.

    With ``prices=False`` it is a download without share prices: no ``precios/`` files and the
    manifest says so. Otherwise the manifest has no ``cotizaciones`` key, like older downloads.
    """
    files: list[dict[str, Any]] = []

    def put(relative: str, content: str) -> None:
        path = folder / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        files.append(
            {"path": relative, "url": f"https://example.invalid/{relative}", "source": "Prueba"}
        )

    for identifier, _, _, scale in COMPANIES:
        put(f"sec/{identifier}.companyfacts.json", json.dumps(companyfacts(scale)))
        put(f"sec/{identifier}.submissions.json", json.dumps(submissions()))
        if prices:
            put(f"precios/{identifier}.nasdaq.json", json.dumps(nasdaq(PRICE_DAYS, 50.0 * scale)))
            put(f"precios/{identifier}.yahoo.json", json.dumps(yahoo(PRICE_DAYS, 50.0 * scale)))
    if european:
        put(f"esef/{EU_ID}.filings.json", json.dumps(esef_index()))
        for year in (2024, 2025):
            put(f"esef/{EU_ID}/{year}-12-31.json", json.dumps(esef_report(year)))
    put("bce/USD.csv", ecb_csv(trading_days(date(2023, 1, 2), date(2026, 8, 14)), 1.10))
    manifest: dict[str, Any] = {
        "creado": "2026-08-15T08:00:00+00:00",
        "ficheros": files,
        "fallos": [],
    }
    if not prices:
        manifest["cotizaciones"] = False
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return folder
