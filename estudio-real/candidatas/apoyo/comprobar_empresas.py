# ruff: noqa: T201  (command-line checker: printing is its output)
"""Check candidate companies for the real-data universe (no prices: SEC, ESEF and ECB only).

Usage (from the project root):
    uv run python <this script> <fragment.yaml> <work folder> [--conceptos]

<fragment.yaml> is a YAML list of company entries in the exact format of estudio-real/universo.yaml.
It downloads their accounts into <work folder> (SEC for `source: sec`, the ESEF annual reports of
filings.xbrl.org for `source: esef`), reads them with the study's provider and prints, per
company: latest filing, latest period in the structured data, the tag chosen for every item, the
debt breakdown of the last balance sheets and every data-quality warning, plus key figures of the
latest fiscal year (in millions) to compare with the published report.

--conceptos also lists, for the ESEF companies, the consolidated concepts of their latest report
that may hold an item (revenue, operating result, depreciation, finance costs, debt, leases…),
to choose the tags and debt lines of the universe entry.
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import yaml

from company_analysis.clock import local_today
from company_analysis.models import FinancialItem, FiscalPeriod
from company_analysis.providers.public.downloads import download, esef_reports, plan
from company_analysis.providers.public.esef import CORE_DIMENSIONS, read_index, report_path
from company_analysis.providers.public.provider import PublicDataProvider
from company_analysis.providers.public.universe import load_universe
from company_analysis.settings import Settings
from company_analysis.study import comparison_date

CANDIDATES = re.compile(
    r"Revenue|GrossProfit|Operating|Ebitda|EBITDA|Depreciation|Amortisation|FinanceCosts|"
    r"InterestExpense|ProfitLossAttributableToOwnersOfParent|CashFlowsFromUsedInOperatingActivities|"
    r"PurchaseOf|^CashAndCashEquivalents$|^Equity$|EquityAttributableToOwnersOfParent|Borrowings|"
    r"Bonds|Debt|Loans|LeaseLiabilities|FinancialLiabilities|NumberOfShares|Deuda|Prestamo|"
    r"Obligacion|Amortizacion|Resultado|Explotacion",
    re.IGNORECASE,
)

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]  # Windows console
fragment, work = Path(sys.argv[1]), Path(sys.argv[2])
concepts = "--conceptos" in sys.argv[3:]
companies = yaml.safe_load(fragment.read_text(encoding="utf-8"))
work.mkdir(parents=True, exist_ok=True)
universe_path = work / "universo.yaml"
universe_path.write_text(
    yaml.safe_dump(
        {
            "name": "Comprobación",
            "description": "Empresas candidatas.",
            "history_start": "2023-01-01",
            "companies": companies,
        },
        allow_unicode=True,
        sort_keys=False,
    ),
    encoding="utf-8",
)
universe = load_universe(universe_path)  # validates the entries (identifiers, debt lines…)
today = local_today()
snapshot = download(
    plan(universe, today, prices=False),
    work / "crudo",
    sec_agent=Settings().http_user_agent,
    progress=lambda r: print("  descargando", r.path),
    then=esef_reports(universe, comparison_date(today)),
)
for failure in snapshot.failures:
    print("FALLO DE DESCARGA:", failure.path, failure.error)
result = PublicDataProvider(universe_path, snapshot.folder).build()

latest_fy: dict[str, dict[FinancialItem, tuple[str, float]]] = defaultdict(dict)
for fact in result.bundle.financial_facts:
    if fact.fiscal_period is FiscalPeriod.FY:
        current = latest_fy[fact.issuer_id].get(fact.item)
        stamp = fact.period_end.isoformat()
        if current is None or stamp >= current[0]:
            latest_fy[fact.issuer_id][fact.item] = (stamp, fact.value)


def esef_concepts(company_id: str) -> None:
    """Consolidated facts of the latest downloaded report that may hold an item, in millions."""
    index = snapshot.folder / f"esef/{company_id}.filings.json"
    entry = next(c for c in universe.companies if c.id == company_id)
    filings = read_index(json.loads(index.read_text(encoding="utf-8")), entry.fiscal_year_end_month)
    reports = [f for f in filings if (snapshot.folder / report_path(company_id, f)).is_file()]
    if not reports:
        print("  (sin informes descargados)")
        return
    document = json.loads(
        (snapshot.folder / report_path(company_id, reports[-1])).read_text(encoding="utf-8")
    )
    rows: dict[str, dict[str, float]] = defaultdict(dict)
    for fact in document["facts"].values():
        dims = fact["dimensions"]
        if set(dims) - CORE_DIMENSIONS or "unit" not in dims or "/" in dims["unit"]:
            continue
        name = dims["concept"].partition(":")[2]
        if not CANDIDATES.search(name):
            continue
        try:
            rows[dims["concept"]][dims["period"]] = float(fact["value"]) / 1e6
        except TypeError, ValueError:
            continue
    print(f"  conceptos consolidados del informe {reports[-1].identifier} (millones):")
    for concept in sorted(rows):
        periods = sorted(rows[concept].items(), reverse=True)[:2]
        values = " | ".join(f"{p[-19:-9]}={v:,.1f}" for p, v in periods)
        print(f"    {concept:<100} {values}")


for quality in result.companies:
    print("=" * 100)
    print(f"{quality.issuer_id} · {quality.name}")
    filing = quality.latest_filing
    if filing:
        print(
            f"  último informe: {filing.form} periodo {filing.period_end} presentado {filing.filed}"
        )
    print(f"  último periodo en los datos estructurados: {quality.latest_period_in_data}")
    for entry in quality.lineage:
        latest = f"{entry.latest[0].value} {entry.latest[1]}" if entry.latest else "—"
        note = f" ({entry.note})" if entry.note else ""
        print(f"  {entry.item.value:<22} {entry.source:<70} {latest}{note}")
    for day, components in sorted(quality.debt_breakdown.items())[-3:]:
        parts = ", ".join(
            f"{c.line}={c.value:,.0f} [{c.tag}]" if c.value is not None else f"{c.line}=— [—]"
            for c in components
        )
        print(f"  deuda {day}: {parts}")
    print("  cifras del último ejercicio (millones):")
    for item, (end, value) in sorted(
        latest_fy[quality.issuer_id].items(), key=lambda kv: kv[0].value
    ):
        print(f"    {item.value:<22} {end}  {value:>14,.1f}")
    for warning in quality.warnings:
        print("  AVISO:", warning)
    entry = next(c for c in universe.companies if c.id == quality.issuer_id)
    if concepts and entry.source == "esef":
        esef_concepts(entry.id)
print("=" * 100)
print("Comprobadas:", ", ".join(q.issuer_id for q in result.companies))
