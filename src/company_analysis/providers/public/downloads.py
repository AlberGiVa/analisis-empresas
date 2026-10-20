"""Download of the public sources into a dated snapshot folder, with a manifest of every file.

Network access lives only here. Each download creates a new folder (``<cache>/<UTC timestamp>/``)
that is never modified afterwards: a load can always be repeated from exactly the same files, and
the manifest records where and when each file was obtained and its SHA-256 fingerprint.
"""

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from company_analysis.clock import utc_now
from company_analysis.providers.public.universe import Universe

MANIFEST = "manifest.json"
TIMEOUT_SECONDS = 60
BROWSER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"  # Nasdaq and Yahoo reject other agents

Fetch = Callable[[str, Mapping[str, str]], bytes]


@dataclass(frozen=True)
class Request:
    path: str  # relative path inside the snapshot
    url: str
    source: str  # human-readable source name
    agent: str  # "sec" (identified agent) or "browser"
    required: bool = True


@dataclass(frozen=True)
class Downloaded:
    path: str
    url: str
    source: str
    retrieved_at: str
    bytes: int
    sha256: str


@dataclass(frozen=True)
class Failure:
    path: str
    url: str
    source: str
    error: str
    required: bool


@dataclass(frozen=True)
class Snapshot:
    folder: Path
    files: list[Downloaded]
    failures: list[Failure]

    @property
    def complete(self) -> bool:
        return not any(failure.required for failure in self.failures)


def plan(universe: Universe, until: date) -> list[Request]:
    """Every file the study needs."""
    start = universe.history_start
    requests: list[Request] = []
    for company in universe.companies:
        cik = company.cik
        requests += [
            Request(
                f"sec/{company.id}.companyfacts.json",
                f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
                "SEC EDGAR (XBRL)",
                "sec",
            ),
            Request(
                f"sec/{company.id}.submissions.json",
                f"https://data.sec.gov/submissions/CIK{cik}.json",
                "SEC EDGAR (registro de informes)",
                "sec",
            ),
            Request(
                f"precios/{company.id}.nasdaq.json",
                f"https://api.nasdaq.com/api/quote/{urllib.parse.quote(company.ticker)}/historical?"
                + urllib.parse.urlencode(
                    {
                        "assetclass": "stocks",
                        "fromdate": start.isoformat(),
                        "todate": until.isoformat(),
                        "limit": 9999,
                    }
                ),
                "Nasdaq (cotizaciones de cierre)",
                "browser",
            ),
            Request(
                f"precios/{company.id}.yahoo.json",
                f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(company.ticker)}?"
                + urllib.parse.urlencode(
                    {
                        "period1": _epoch(start),
                        "period2": _epoch(until) + 86_400,
                        "interval": "1d",
                    }
                ),
                "Yahoo Finance (contraste de cotizaciones)",
                "browser",
                required=False,
            ),
        ]
    for currency in universe.currencies:
        requests.append(
            Request(
                f"bce/{currency}.csv",
                f"https://data-api.ecb.europa.eu/service/data/EXR/D.{currency}.EUR.SP00.A?"
                + urllib.parse.urlencode({"startPeriod": start.isoformat(), "format": "csvdata"}),
                "Banco Central Europeo (tipos de cambio)",
                "browser",
            )
        )
    return requests


def _epoch(day: date) -> int:
    return (day - date(1970, 1, 1)).days * 86_400


def http_fetch(url: str, headers: Mapping[str, str]) -> bytes:
    request = urllib.request.Request(url, headers=dict(headers))
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        body: bytes = response.read()
    return body


def _describe(error: Exception) -> str:
    if isinstance(error, urllib.error.HTTPError):
        return f"respuesta HTTP {error.code}"
    if isinstance(error, urllib.error.URLError):
        return f"sin conexión ({error.reason})"
    return f"{type(error).__name__}: {error}"


def download(
    requests: Sequence[Request],
    cache_dir: Path,
    *,
    sec_agent: str,
    fetch: Fetch = http_fetch,
    pause_seconds: float = 0.15,
    progress: Callable[[Request], None] | None = None,
) -> Snapshot:
    """Download everything into a new snapshot folder and write its manifest."""
    stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    folder = cache_dir / stamp
    files: list[Downloaded] = []
    failures: list[Failure] = []
    for request in requests:
        if progress:
            progress(request)
        agent = sec_agent if request.agent == "sec" else BROWSER_AGENT
        headers = {"User-Agent": agent, "Accept": "application/json, text/csv, */*"}
        try:
            body = fetch(request.url, headers)
        except (OSError, ValueError) as error:  # URLError and HTTPError are OSError
            failures.append(
                Failure(
                    request.path, request.url, request.source, _describe(error), request.required
                )
            )
            continue
        target = folder / request.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        files.append(
            Downloaded(
                path=request.path,
                url=request.url,
                source=request.source,
                retrieved_at=utc_now().isoformat(timespec="seconds"),
                bytes=len(body),
                sha256=hashlib.sha256(body).hexdigest(),
            )
        )
        if pause_seconds:
            time.sleep(pause_seconds)  # well below the SEC limit of 10 requests per second
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {
        "creado": utc_now().isoformat(timespec="seconds"),
        "identificacion_sec": sec_agent,
        "ficheros": [asdict(f) for f in files],
        "fallos": [asdict(f) for f in failures],
    }
    (folder / MANIFEST).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return Snapshot(folder, files, failures)


def latest_snapshot(cache_dir: Path) -> Path | None:
    """Most recent snapshot that finished (it has a manifest)."""
    if not cache_dir.is_dir():
        return None
    complete = [d for d in cache_dir.iterdir() if d.is_dir() and (d / MANIFEST).is_file()]
    return max(complete, key=lambda d: d.name, default=None)


def read_manifest(folder: Path) -> dict[str, object]:
    data: dict[str, object] = json.loads((folder / MANIFEST).read_text(encoding="utf-8"))
    return data
