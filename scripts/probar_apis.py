"""Check the free public APIs proposed as future data sources (no keys or sign-up needed).

    uv run python scripts/probar_apis.py

For each source it prints whether it answers, how long it takes and one sample value. Nothing is
stored: this is a connection test, not a data provider. Messages are in Spanish (user interface).
"""

import csv
import io
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from company_analysis.formatting import format_date, format_number
from company_analysis.settings import Settings

TIMEOUT_SECONDS = 40
ECB = "https://data-api.ecb.europa.eu/service/data"
SAMPLE_ISIN = "ES0144580Y14"  # Iberdrola ordinary share
SAMPLE_BOND_ISIN = "XS2289133915"  # UniCredit 0.325 % 2026 (matured: shows the "Terminated" status)
SAMPLE_SEC_CIK = "0000320193"  # Apple Inc.


@dataclass(frozen=True)
class Source:
    name: str
    browser: bool  # answers browser requests (CORS), so it can be tried from the showcase page
    check: Callable[[str], str]  # receives the User-Agent, returns a sample value in Spanish


def fetch(url: str, user_agent: str, payload: object | None = None) -> bytes:
    headers = {"User-Agent": user_agent, "Accept": "application/json, text/csv"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        body: bytes = response.read()
    return body


def fetch_json(url: str, user_agent: str, payload: object | None = None) -> Any:
    return json.loads(fetch(url, user_agent, payload))


def ecb_last(series: str, user_agent: str) -> tuple[date, float]:
    text = fetch(f"{ECB}/{series}?lastNObservations=1&format=csvdata", user_agent).decode()
    last = list(csv.DictReader(io.StringIO(text)))[-1]
    return date.fromisoformat(last["TIME_PERIOD"]), float(last["OBS_VALUE"])


def ecb_fx(user_agent: str) -> str:
    day, value = ecb_last("EXR/D.USD.EUR.SP00.A", user_agent)
    return f"1 EUR = {format_number(value, 4)} USD ({format_date(day)})"


def ecb_yield_curve(user_agent: str) -> str:
    day, value = ecb_last("YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y", user_agent)
    rate = format_number(value, 2)
    return f"Deuda pública AAA de la zona euro a 10 años: {rate} % ({format_date(day)})"


def ecb_estr(user_agent: str) -> str:
    day, value = ecb_last("EST/B.EU000A2X2A25.WT", user_agent)
    return f"€STR: {format_number(value, 3)} % ({format_date(day)})"


def gleif(user_agent: str) -> str:
    query = urllib.parse.urlencode({"filter[isin]": SAMPLE_ISIN})
    record = fetch_json(f"https://api.gleif.org/api/v1/lei-records?{query}", user_agent)["data"][0]
    entity = record["attributes"]["entity"]
    return (
        f"{SAMPLE_ISIN} → {entity['legalName']['name']}, LEI {record['id']} "
        f"({entity['legalAddress']['country']}, {entity['status']})"
    )


def world_bank(user_agent: str) -> str:
    url = "https://api.worldbank.org/v2/country/ES/indicator/NY.GDP.MKTP.KD.ZG?format=json&mrnev=1"
    row = fetch_json(url, user_agent)[1][0]
    return f"Crecimiento del PIB de España en {row['date']}: {format_number(row['value'], 1)} %"


def sec_edgar(user_agent: str) -> str:
    base = "https://data.sec.gov/api/xbrl/companyconcept"
    url = f"{base}/CIK{SAMPLE_SEC_CIK}/us-gaap/NetIncomeLoss.json"
    concept = fetch_json(url, user_agent)
    annual = [f for f in concept["units"]["USD"] if f.get("form") == "10-K" and f.get("fp") == "FY"]
    last = max(annual, key=lambda fact: (fact["end"], fact["filed"]))
    closing = format_date(date.fromisoformat(last["end"]))
    filed = format_date(date.fromisoformat(last["filed"]))
    amount = format_number(last["val"] / 1e6, 0)
    return (
        f"{concept['entityName']}: beneficio neto del ejercicio cerrado el {closing} = "
        f"{amount} M USD, presentado el {filed}"
    )


def fred(user_agent: str) -> str:
    text = fetch("https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLHE00EHYIOAS", user_agent)
    rows = list(csv.reader(io.StringIO(text.decode())))[1:]
    valid = [(day, value) for day, value in rows if value not in ("", ".")]
    first_day, (last_day, last_value) = valid[0][0], valid[-1]
    spread = format_number(float(last_value) * 100, 0)  # FRED publishes it in percentage points
    return (
        f"Diferencial (OAS) del high yield en euros: {spread} pb "
        f"({format_date(date.fromisoformat(last_day))}); historia desde "
        f"{format_date(date.fromisoformat(first_day))}"
    )


def esma_firds(user_agent: str) -> str:
    query = urllib.parse.urlencode(
        {"q": f"isin:{SAMPLE_BOND_ISIN} AND type_s:parent", "rows": 1, "wt": "json"}
    )
    url = f"https://registers.esma.europa.eu/solr/esma_registers_firds/select?{query}"
    bond = fetch_json(url, user_agent)["response"]["docs"][0]
    maturity = date.fromisoformat(bond["bnd_maturity_date"][:10])
    nominal = float(bond["bnd_nmnl_value_total"]) / 1e6
    coupon = format_number(float(bond["bnd_fixed_rate"]), 3)  # the register returns text
    return (
        f"{SAMPLE_BOND_ISIN}: {bond['gnr_full_name']}; cupón {coupon} %, "
        f"vencimiento {format_date(maturity)}, {format_number(nominal, 0)} M "
        f"{bond['gnr_notional_curr_code']}, emisor LEI {bond['lei']}"
    )


def openfigi(user_agent: str) -> str:
    jobs = [{"idType": "ID_ISIN", "idValue": SAMPLE_ISIN, "exchCode": "SM"}]
    match = fetch_json("https://api.openfigi.com/v3/mapping", user_agent, jobs)[0]["data"][0]
    listing = f"{match['ticker']} {match['exchCode']}"
    return f"{SAMPLE_ISIN} → {listing} ({match['name']}, FIGI {match['figi']})"


SOURCES = (
    Source("BCE · Tipos de cambio", True, ecb_fx),
    Source("BCE · Curva de tipos", True, ecb_yield_curve),
    Source("BCE · €STR", True, ecb_estr),
    Source("GLEIF · LEI de emisores", True, gleif),
    Source("Banco Mundial · Macro", True, world_bank),
    Source("SEC EDGAR · Estados financieros", False, sec_edgar),
    Source("FRED · Diferenciales ICE BofA", False, fred),
    Source("ESMA FIRDS · Datos de bonos", False, esma_firds),
    Source("OpenFIGI · ISIN a ticker", False, openfigi),
)


def describe_error(error: Exception) -> str:
    if isinstance(error, urllib.error.HTTPError):
        return f"respuesta HTTP {error.code} ({error.reason})"
    if isinstance(error, urllib.error.URLError):
        return f"sin conexión ({error.reason})"
    if isinstance(error, TimeoutError):
        return f"no responde en {TIMEOUT_SECONDS} s"
    return f"respuesta inesperada ({type(error).__name__}: {error})"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    user_agent = Settings().http_user_agent
    print(f"Probando {len(SOURCES)} APIs públicas y gratuitas (identificación: {user_agent!r})\n")
    failures = 0
    for source in SOURCES:
        where = "navegador y Python" if source.browser else "solo Python"
        started = time.perf_counter()
        try:
            sample = source.check(user_agent)
        except (OSError, ValueError, KeyError, IndexError, TypeError) as error:
            failures += 1
            print(f"  ✗ {source.name} [{where}]: {describe_error(error)}")
            continue
        elapsed = (time.perf_counter() - started) * 1000
        print(f"  ✓ {source.name} [{where}, {format_number(elapsed, 0)} ms]\n      {sample}")
    print(
        f"\n{len(SOURCES) - failures} de {len(SOURCES)} fuentes responden. "
        "Nada de esto se ha guardado en la base de datos."
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
