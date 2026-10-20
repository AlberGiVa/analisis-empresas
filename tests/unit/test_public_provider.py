"""Bundle and data-quality review built from a downloaded snapshot (synthetic responses)."""

import json
from collections.abc import Mapping
from datetime import date
from pathlib import Path

import pytest

from company_analysis.models import FinancialItem
from company_analysis.providers.public.downloads import (
    MANIFEST,
    Request,
    download,
    latest_snapshot,
    plan,
)
from company_analysis.providers.public.provider import (
    PublicDataProvider,
    PublicDataResult,
    SnapshotError,
    standalone_quarters,
)
from company_analysis.providers.public.universe import UniverseError, load_universe
from tests import public_samples


@pytest.fixture(scope="module")
def result(tmp_path_factory: pytest.TempPathFactory) -> PublicDataResult:
    root = tmp_path_factory.mktemp("estudio")
    universe = public_samples.write_universe(root)
    snapshot = public_samples.write_snapshot(root / "datos" / "crudo" / "20260815T080000Z")
    return PublicDataProvider(universe, snapshot).build()


def warnings_of(result: PublicDataResult, issuer_id: str) -> list[str]:
    return next(q.warnings for q in result.companies if q.issuer_id == issuer_id)


def test_the_snapshot_becomes_a_valid_bundle(result: PublicDataResult) -> None:
    counts = result.bundle.row_counts()
    assert counts["issuers"] == 2
    assert counts["equities"] == 2
    assert counts["equity_prices"] == 2 * len(public_samples.PRICE_DAYS)
    assert counts["bonds"] == 0
    assert result.created.startswith("2026-08-15")
    assert result.fx[0].currency == "USD"


def test_a_filing_not_yet_in_the_structured_data_is_reported(result: PublicDataResult) -> None:
    assert any(
        "todavía no está en los datos estructurados" in w for w in warnings_of(result, "ZZAA")
    )


def test_a_debt_line_not_presented_is_reported(result: PublicDataResult) -> None:
    assert any("Préstamos a corto plazo no aparece" in w for w in warnings_of(result, "ZZAA"))


def test_an_impaired_quarter_is_reported_as_unusual(result: PublicDataResult) -> None:
    quality = next(q for q in result.companies if q.issuer_id == "ZZAA")
    unusual = [w for w in quality.warnings if "atípico" in w]
    assert len(unusual) == 1
    assert "30/06/2026" in unusual[0]
    assert quality.distorted_ebitda


def test_prices_agree_with_the_second_source(result: PublicDataResult) -> None:
    quality = result.companies[0]
    assert quality.compared_days == len(public_samples.PRICE_DAYS)
    assert quality.max_price_difference == 0.0
    assert not any("Cotizaciones" in w or "Mercado" in w for w in quality.warnings)


def test_standalone_quarters_come_from_cumulative_periods(result: PublicDataResult) -> None:
    facts = [f for f in result.bundle.financial_facts if f.issuer_id == "ZZAA"]
    quarters = dict(standalone_quarters(facts, FinancialItem.REVENUE))
    assert quarters[date(2026, 3, 31)] == 280.0
    assert quarters[date(2026, 6, 30)] == 300.0
    assert quarters[date(2025, 12, 31)] == 290.0  # FY minus 9M


def test_a_missing_file_stops_the_load(tmp_path: Path) -> None:
    universe = public_samples.write_universe(tmp_path)
    snapshot = public_samples.write_snapshot(tmp_path / "snapshot")
    (snapshot / "precios" / "ZZBB.nasdaq.json").unlink()
    with pytest.raises(SnapshotError, match=r"ZZBB\.nasdaq\.json"):
        PublicDataProvider(universe, snapshot).fetch()


def test_an_invalid_universe_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "universo.yaml"
    path.write_text("name: x\ndescription: y\nhistory_start: 2026-01-01\ncompanies: []\n")
    with pytest.raises(UniverseError):
        load_universe(path)


# --- Downloads ---------------------------------------------------------------------------------
def test_the_plan_covers_every_source(tmp_path: Path) -> None:
    universe = load_universe(public_samples.write_universe(tmp_path))
    requests = plan(universe, date(2026, 8, 15))
    assert len(requests) == 2 * 4 + 1
    assert any("CIK0000000001.json" in r.url and r.agent == "sec" for r in requests)
    assert all(r.required for r in requests if not r.path.endswith(".yahoo.json"))


def test_download_writes_files_and_a_manifest(tmp_path: Path) -> None:
    requests = [
        Request("sec/A.json", "https://example.invalid/a", "Prueba", "sec"),
        Request("precios/A.yahoo.json", "https://example.invalid/b", "Prueba", "browser", False),
    ]
    agents: list[str] = []

    def fetch(url: str, headers: Mapping[str, str]) -> bytes:
        agents.append(headers["User-Agent"])
        if url.endswith("/b"):
            raise OSError("sin red")
        return b'{"ok": true}'

    snapshot = download(
        requests, tmp_path, sec_agent="Prueba contacto", fetch=fetch, pause_seconds=0
    )
    assert snapshot.complete  # only an optional file failed
    assert (snapshot.folder / "sec" / "A.json").read_bytes() == b'{"ok": true}'
    manifest = json.loads((snapshot.folder / MANIFEST).read_text(encoding="utf-8"))
    assert manifest["ficheros"][0]["sha256"] == snapshot.files[0].sha256
    assert manifest["fallos"][0]["path"] == "precios/A.yahoo.json"
    assert agents[0] == "Prueba contacto"
    assert latest_snapshot(tmp_path) == snapshot.folder


def test_a_failed_required_file_makes_the_download_incomplete(tmp_path: Path) -> None:
    def fetch(url: str, headers: Mapping[str, str]) -> bytes:
        raise OSError("sin red")

    request = Request("sec/A.json", "https://example.invalid/a", "Prueba", "sec")
    snapshot = download([request], tmp_path, sec_agent="x", fetch=fetch, pause_seconds=0)
    assert not snapshot.complete
