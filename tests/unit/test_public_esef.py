"""Annual reports of European listed companies (ESEF, filings.xbrl.org): synthetic responses."""

import json
from collections.abc import Mapping
from datetime import date
from pathlib import Path

import pytest

from company_analysis.models import FinancialFact, FinancialItem, FiscalPeriod
from company_analysis.providers.public.downloads import download, esef_reports, plan
from company_analysis.providers.public.esef import (
    EsefFiling,
    company_facts,
    filings_to_download,
    period,
    read_index,
)
from company_analysis.providers.public.provider import PublicDataProvider
from company_analysis.providers.public.sec import IFRS, DebtLine, extract_financials
from company_analysis.providers.public.universe import load_universe
from tests import public_samples
from tests.public_samples import EU_ID, EU_LEI

DEBT = [
    DebtLine("Deuda a corto", ("CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings",)),
    DebtLine("Deuda a largo", ("NoncurrentPortionOfNoncurrentBorrowings",), required=True),
]


def documents() -> list[tuple[EsefFiling, Mapping[str, object]]]:
    filings = read_index(public_samples.esef_index(), 12)
    return [(filing, public_samples.esef_report(filing.period_end.year)) for filing in filings]


def test_period_ends_are_exclusive() -> None:
    assert period("2025-01-01T00:00:00/2026-01-01T00:00:00") == (
        date(2025, 1, 1),
        date(2025, 12, 31),
    )
    assert period("2026-01-01T00:00:00") == (None, date(2025, 12, 31))
    assert period("2026-02-01") == (None, date(2026, 1, 31))


def test_a_report_listed_twice_keeps_the_one_public_first() -> None:
    filings = read_index(public_samples.esef_index(), 12)
    assert [(f.period_end, f.available) for f in filings] == [
        (date(2024, 12, 31), date(2025, 2, 27)),  # published by the source, not when added
        (date(2025, 12, 31), date(2026, 2, 26)),
    ]
    assert filings[0].identifier.endswith("ESEF-ES-1")


def test_interim_reports_are_left_out() -> None:
    index = public_samples.esef_index()
    interim = json.loads(json.dumps(index["data"][-1]))
    interim["attributes"] |= {"period_end": "2026-06-30", "fxo_id": "half-year", "published": None}
    index["data"].append(interim)
    assert [f.period_end.year for f in read_index(index, 12)] == [2024, 2025]


def test_the_reports_to_download_cover_every_analysis_date() -> None:
    filings = read_index(public_samples.esef_index(), 12)
    after_both = filings_to_download(filings, date(2026, 6, 30))
    assert [f.period_end.year for f in after_both] == [2025]  # it carries 2024 as comparative
    between = filings_to_download(filings, date(2025, 12, 31))
    assert [f.period_end.year for f in between] == [2024, 2025]


def test_only_the_consolidated_figures_of_the_company_are_read() -> None:
    facts = company_facts(documents(), EU_LEI)
    revenue = facts["facts"]["ifrs-full"]["Revenue"]["units"]["EUR"]
    values = {(entry["end"], entry["filed"], entry["val"]) for entry in revenue}
    # No segment (600), no other entity (5); comparatives repeated by the later report.
    assert values == {
        ("2023-12-31", "2025-02-27", 950e6),
        ("2024-12-31", "2025-02-27", 1000e6),
        ("2024-12-31", "2026-02-26", 1000e6),
        ("2025-12-31", "2026-02-26", 1100e6),
    }
    assert "BasicEarningsPerShare" not in facts["facts"]["ifrs-full"]  # a ratio
    assert "ifrs" not in facts["facts"]  # the other prefix of the IFRS taxonomy
    assert all(e["form"] == "ESEF" for e in revenue)


def _facts(item: FinancialItem, end: date) -> list[FinancialFact]:
    extraction = extract_financials(
        EU_ID,
        company_facts(documents(), EU_LEI),
        currency="EUR",
        fiscal_year_end_month=12,
        debt_lines=DEBT,
        standard=IFRS,
    )
    return sorted(
        (f for f in extraction.facts if f.item is item and f.period_end == end),
        key=lambda f: f.published_at,
    )


def test_ifrs_accounts_give_the_items_of_the_analysis() -> None:
    (revenue,) = _facts(FinancialItem.REVENUE, date(2025, 12, 31))
    assert (revenue.fiscal_period, revenue.value, revenue.currency) == (
        FiscalPeriod.FY,
        1100.0,
        "EUR",
    )
    assert revenue.published_at == date(2026, 2, 26)
    (ebitda,) = _facts(FinancialItem.EBITDA, date(2025, 12, 31))
    assert ebitda.value == pytest.approx(130 + 45)
    (debt,) = _facts(FinancialItem.TOTAL_DEBT, date(2025, 12, 31))
    assert debt.value == pytest.approx(25 + 280)
    (interest,) = _facts(FinancialItem.INTEREST_EXPENSE, date(2025, 12, 31))
    assert interest.value == 16.0
    # 2024 was first public in its own report: the later one repeats the same figure.
    assert [f.published_at for f in _facts(FinancialItem.REVENUE, date(2024, 12, 31))] == [
        date(2025, 2, 27)
    ]


def test_a_tag_fixed_with_a_minus_sign_is_read_with_its_sign_changed() -> None:
    facts = company_facts(documents(), EU_LEI)
    capex = facts["facts"]["ifrs-full"][
        "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"
    ]
    facts["facts"]["eu"] = {
        "Inversiones": {"units": {"EUR": [{**e, "val": -e["val"]} for e in capex["units"]["EUR"]]}}
    }
    extraction = extract_financials(
        EU_ID,
        facts,
        currency="EUR",
        fiscal_year_end_month=12,
        debt_lines=DEBT,
        overrides={FinancialItem.CAPITAL_EXPENDITURE: ["-eu:Inversiones"]},
        standard=IFRS,
    )
    capex_2025 = [
        f.value
        for f in extraction.facts
        if f.item is FinancialItem.CAPITAL_EXPENDITURE and f.period_end == date(2025, 12, 31)
    ]
    assert capex_2025 == [55.0]


def test_a_tag_fixed_as_a_sum_adds_both_lines() -> None:
    extraction = extract_financials(
        EU_ID,
        company_facts(documents(), EU_LEI),
        currency="EUR",
        fiscal_year_end_month=12,
        debt_lines=DEBT,
        overrides={
            FinancialItem.CAPITAL_EXPENDITURE: [
                "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"
                "+DepreciationAndAmortisationExpense"
            ]
        },
        standard=IFRS,
    )
    capex_2025 = [
        f.value
        for f in extraction.facts
        if f.item is FinancialItem.CAPITAL_EXPENDITURE and f.period_end == date(2025, 12, 31)
    ]
    assert capex_2025 == [55.0 + 45.0]  # any two lines of the same statement add up


def test_a_download_fetches_the_reports_its_index_lists(tmp_path: Path) -> None:
    universe = load_universe(public_samples.write_universe(tmp_path, european=True))
    requests = plan(universe, date(2026, 8, 15), prices=False)
    assert f"esef/{EU_ID}.filings.json" in [r.path for r in requests]
    assert not [r for r in requests if r.path.startswith("precios/")]
    bodies = {
        "filings?": json.dumps(public_samples.esef_index()).encode(),
        "report.json": json.dumps(public_samples.esef_report(2025)).encode(),
    }
    asked: list[str] = []

    def fetch(url: str, headers: Mapping[str, str]) -> bytes:
        asked.append(url)
        return next((body for key, body in bodies.items() if key in url), b"{}")

    snapshot = download(
        requests,
        tmp_path / "crudo",
        sec_agent="Prueba contacto",
        fetch=fetch,
        pause_seconds=0,
        then=esef_reports(universe, date(2026, 6, 30)),
    )
    assert (snapshot.folder / f"esef/{EU_ID}/2025-12-31.json").is_file()
    assert asked[-1] == f"https://filings.xbrl.org/{EU_LEI}/2025-12-31/ESEF/ES/0/report.json"
    manifest = json.loads((snapshot.folder / "manifest.json").read_text(encoding="utf-8"))
    assert f"esef/{EU_ID}/2025-12-31.json" in [f["path"] for f in manifest["ficheros"]]


def test_the_provider_reads_european_and_us_companies(tmp_path: Path) -> None:
    universe = public_samples.write_universe(tmp_path, european=True)
    snapshot = public_samples.write_snapshot(tmp_path / "descarga", prices=False, european=True)
    result = PublicDataProvider(universe, snapshot).build()
    quality = {q.issuer_id: q for q in result.companies}[EU_ID]
    assert quality.latest_filing is not None
    assert (quality.latest_filing.form, quality.latest_filing.filed) == ("ESEF", date(2026, 2, 26))
    assert quality.latest_period_in_data == date(2025, 12, 31)
    european = [f for f in result.bundle.financial_facts if f.issuer_id == EU_ID]
    assert {f.currency for f in european if f.currency} == {"EUR"}
    assert not [p for p in result.bundle.equity_prices if p.isin.startswith("ZZEZZEU")]
