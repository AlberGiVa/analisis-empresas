"""Annual reports of European listed companies in XBRL (ESEF), from filings.xbrl.org.

Since 2021 every company listed on a regulated market of the European Union publishes its annual
financial report in Inline XBRL (ESEF, IFRS); British companies keep the same format.
filings.xbrl.org, run by XBRL International, collects them and offers each one as xBRL-JSON, and
says there are no restrictions on the ways the data can be used.

Only the consolidated figures are read (facts without dimensions: no segment nor breakdown), and
they are converted to the shape of the SEC company facts so that the same point-in-time reader
(``sec.py``) applies. A filing's publication date is the one its source gives; when it gives none,
the date the filing reached filings.xbrl.org, which is later: a figure is never used before it was
public. Only annual reports are in the format, so the latest twelve months are the latest year.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from company_analysis.providers.public.sec import ESEF_FORM, closes_fiscal_year

SITE = "https://filings.xbrl.org"
IFRS_PREFIX = "ifrs-full"
CORE_DIMENSIONS = frozenset({"concept", "entity", "period", "unit", "language"})
MAX_FILINGS = 3  # reports downloaded per company


@dataclass(frozen=True)
class EsefFiling:
    """One annual report in the index of filings.xbrl.org."""

    period_end: date
    available: date  # published, or added to filings.xbrl.org when the source gives no date
    identifier: str  # fxo_id: LEI, period end, format, country and sequence
    json_url: str | None  # xBRL-JSON, relative to the site; None if it could not be processed
    published_by_source: bool  # False: ``available`` is the date it reached filings.xbrl.org


def index_url(lei: str) -> str:
    return f"{SITE}/api/entities/{lei}/filings?page%5Bsize%5D=100"


def read_index(index: Mapping[str, Any], fiscal_year_end_month: int) -> list[EsefFiling]:
    """The company's annual reports, one per period end, oldest first.

    Interim reports (some companies also publish them in the format) are left out: their period
    does not close a fiscal year. The same report may be listed twice (it reached filings.xbrl.org
    from two sources): the one known to have been public first is kept.
    """
    best: dict[date, EsefFiling] = {}
    for item in index.get("data", []):
        attributes = item.get("attributes", {})
        published = attributes.get("published")
        added = attributes.get("date_added")
        if not attributes.get("period_end") or not (published or added):
            continue
        period_end = date.fromisoformat(attributes["period_end"][:10])
        if not closes_fiscal_year(period_end, fiscal_year_end_month):
            continue
        filing = EsefFiling(
            period_end=period_end,
            available=date.fromisoformat(str(published or added)[:10]),
            identifier=str(attributes.get("fxo_id", item.get("id", ""))),
            json_url=attributes.get("json_url"),
            published_by_source=bool(published),
        )
        current = best.get(filing.period_end)
        if current is None or (
            (filing.json_url is not None, -filing.available.toordinal())
            > (current.json_url is not None, -current.available.toordinal())
        ):
            best[filing.period_end] = filing
    return [best[day] for day in sorted(best)]


def filings_to_download(filings: Sequence[EsefFiling], since: date) -> list[EsefFiling]:
    """The latest annual report public on ``since`` and every later one (at most ``MAX_FILINGS``).

    That is enough to analyse any date from ``since`` on; earlier years come from the comparative
    figures each report repeats.
    """
    usable = [f for f in filings if f.json_url]
    before = [f for f in usable if f.available <= since]
    chosen = [max(before, key=lambda f: f.available)] if before else []
    chosen += [f for f in usable if f.available > since]
    return sorted(chosen, key=lambda f: f.period_end)[-MAX_FILINGS:]


def report_path(company_id: str, filing: EsefFiling) -> str:
    """Where a report is saved inside a download."""
    return f"esef/{company_id}/{filing.period_end.isoformat()}.json"


def _day(moment: str, *, end: bool) -> date:
    """A date of an xBRL-JSON period. Ends are exclusive: midnight closes the previous day."""
    day = date.fromisoformat(moment[:10])
    time = moment[11:]
    if end and time in ("", "00:00:00"):
        return day - timedelta(days=1)
    return day


def period(text: str) -> tuple[date | None, date]:
    """(start, end) of a duration, (None, day) of an instant; both days included."""
    if "/" in text:
        start, end = text.split("/")
        return _day(start, end=False), _day(end, end=True)
    return None, _day(text, end=True)


def _prefixes(document: Mapping[str, Any]) -> dict[str, str]:
    """Prefix of each namespace, with the IFRS taxonomy always as ``ifrs-full``."""
    namespaces = document.get("documentInfo", {}).get("namespaces", {})
    return {
        prefix: IFRS_PREFIX
        if "xbrl.ifrs.org/taxonomy/" in uri and uri.rstrip("/").endswith("/ifrs-full")
        else prefix
        for prefix, uri in namespaces.items()
    }


def company_facts(
    documents: Iterable[tuple[EsefFiling, Mapping[str, Any]]], lei: str
) -> dict[str, Any]:
    """The consolidated facts of the reports, shaped like SEC company facts (``sec.read_facts``).

    Each fact keeps the report it comes from (accession) and its publication date (filed).
    """
    facts: dict[str, dict[str, dict[str, Any]]] = {}
    for filing, document in documents:
        prefixes = _prefixes(document)
        for fact in document.get("facts", {}).values():
            dimensions = fact.get("dimensions", {})
            unit = dimensions.get("unit")
            if set(dimensions) - CORE_DIMENSIONS or not unit or "/" in unit:
                continue  # a breakdown, a text or a ratio
            if str(dimensions.get("entity", "")).rpartition(":")[2] != lei:
                continue
            try:
                value = float(fact["value"])
            except KeyError, TypeError, ValueError:
                continue
            prefix, _, name = str(dimensions["concept"]).partition(":")
            start, end = period(str(dimensions["period"]))
            entry: dict[str, Any] = {
                "end": end.isoformat(),
                "val": value,
                "accn": filing.identifier,
                "form": ESEF_FORM,
                "filed": filing.available.isoformat(),
            }
            if start is not None:
                entry["start"] = start.isoformat()
            units = facts.setdefault(prefixes.get(prefix, prefix), {}).setdefault(
                name, {"units": {}}
            )["units"]
            units.setdefault(unit.rpartition(":")[2], []).append(entry)
    return {"facts": facts}


__all__ = [
    "MAX_FILINGS",
    "SITE",
    "EsefFiling",
    "company_facts",
    "filings_to_download",
    "index_url",
    "period",
    "read_index",
    "report_path",
]
