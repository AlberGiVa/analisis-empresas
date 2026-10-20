"""The public website, built end to end from a synthetic download without prices (no network)."""

import re
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from company_analysis.settings import PROJECT_ROOT, Settings
from company_analysis.web import SAMPLE_CASES, app
from tests import public_samples

runner = CliRunner()
DATES = ["--fecha", "2026-06-30", "--fecha", "2026-08-14"]
LINK = re.compile(r'(?:href|src)="([^"]+)"')


def _study(root: Path, *, prices: bool) -> Path:
    """A study folder like ``estudio-real/`` with a synthetic download; returns the download."""
    shutil.copy(PROJECT_ROOT / "estudio-real" / "metodologia-web.yaml", root)
    public_samples.write_universe(root)
    return public_samples.write_snapshot(root / "descarga", prices=prices)


def _build(target: Path, snapshot: Path, *options: str) -> str:
    result = runner.invoke(
        app, ["construir", "--salida", str(target), "--descarga", str(snapshot), *DATES, *options]
    )
    assert result.exit_code == 0, result.output
    return result.output


@pytest.fixture(scope="module")
def site(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("estudio")
    snapshot = _study(root, prices=False)
    target = tmp_path_factory.mktemp("web") / "sitio"
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("ANALYSIS_STUDY_DIR", str(root))
        main_database = Settings().db_path
        existed = main_database.exists()
        _build(target, snapshot, "--pendientes", str(target.parent / PENDING))
        assert main_database.exists() == existed  # the main database is never touched
    assert not (root / "datos").exists()  # nor the study's
    return target


PENDING = "pendientes.txt"

# Texts of the synthetic test data (tests/public_samples.py): not part of the published catalog.
TEST_ONLY_TEXTS = {"Universo de prueba", "Empresas inventadas para las pruebas", "Prueba:"}
TEST_ONLY_PREFIX = "https://example.invalid/"


def test_the_english_site_mirrors_the_spanish_one(site: Path) -> None:
    spanish = [p.relative_to(site) for p in _pages(site) if p.relative_to(site).parts[0] != "en"]
    for relative in spanish:
        english = site / "en" / relative
        assert english.is_file(), relative
        assert '<html lang="en">' in english.read_text(encoding="utf-8"), relative
    home = (site / "index.html").read_text(encoding="utf-8")
    english_home = (site / "en" / "index.html").read_text(encoding="utf-8")
    assert 'href="en/index.html" hreflang="en" lang="en" translate="no">English</a>' in home
    assert 'href="../index.html" hreflang="es" lang="es" translate="no">Español</a>' in english_home
    ficha = (site / "en" / "reales" / "fichas" / "ZZAA.html").read_text(encoding="utf-8")
    assert 'href="../../../reales/fichas/ZZAA.html"' in ficha


def test_everything_on_the_english_site_is_translated(site: Path) -> None:
    pending = (site.parent / PENDING).read_text(encoding="utf-8").splitlines()
    left = {text for text in pending if not text.startswith(TEST_ONLY_PREFIX)}
    assert left - TEST_ONLY_TEXTS == set()


def _pages(site: Path) -> list[Path]:
    return sorted(site.rglob("*.html"))


def test_every_section_is_built(site: Path) -> None:
    for page in (
        "index.html",
        "reales/index.html",
        "reales/ranking.html",
        "reales/ranking.csv",
        "reales/fichas/ZZAA.html",
        "ejemplo/index.html",
        "ejemplo/ranking.html",
        "ejemplo/ranking.csv",
        "como-funciona.html",
        ".nojekyll",
        "marca/luceiro-logo.webp",
        "presentacion.html",
    ):
        assert (site / page).is_file(), page
    assert len(list((site / "ejemplo" / "fichas").glob("*.html"))) == len(SAMPLE_CASES)
    home = (site / "index.html").read_text(encoding="utf-8")
    assert "Universo de prueba" in home
    assert 'href="reales/index.html"' in home


def test_every_page_has_the_navigation_and_working_links(site: Path) -> None:
    for page in _pages(site):
        html = page.read_text(encoding="utf-8")
        assert '<nav class="nav"' in html, page
        assert '<meta name="robots" content="noindex, nofollow">' in html, page
        for link in LINK.findall(html):
            if link.startswith(("http://", "https://", "#", "data:")) or "${" in link:
                continue
            target = (page.parent / link.split("#")[0]).resolve()
            assert target.is_file(), f"{page.relative_to(site)} enlaza a {link}, que no existe"


def test_the_real_companies_never_show_share_prices(site: Path) -> None:
    for page in (site / "reales").rglob("*.html"):
        html = page.read_text(encoding="utf-8")
        assert "Nasdaq" not in html, page
        assert "Yahoo" not in html, page
    study = (site / "reales" / "index.html").read_text(encoding="utf-8")
    assert "Rentabilidad frente a apalancamiento" in study
    assert ">PER</th>" not in study
    assert ">Capitaliz.</th>" not in study
    assert "2026.10-web-1" in study


def test_the_website_never_shows_the_journal_nor_local_paths(site: Path) -> None:
    for page in _pages(site):
        html = page.read_text(encoding="utf-8")
        assert "<h2>Diario del analista</h2>" not in html, page  # the section with the notes
        assert str(PROJECT_ROOT) not in html, page
        assert str(site.parent) not in html, page


def test_a_download_with_prices_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = _study(tmp_path, prices=True)
    monkeypatch.setenv("ANALYSIS_STUDY_DIR", str(tmp_path))
    target = tmp_path / "sitio"
    result = runner.invoke(
        app, ["construir", "--salida", str(target), "--descarga", str(snapshot), *DATES]
    )
    assert result.exit_code == 1
    assert "tiene cotizaciones" in result.output
    assert not target.exists()


def test_a_folder_that_is_not_a_built_website_is_never_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = _study(tmp_path, prices=False)
    monkeypatch.setenv("ANALYSIS_STUDY_DIR", str(tmp_path))
    foreign = tmp_path / "otra"
    foreign.mkdir()
    (foreign / "importante.txt").write_text("no borrar", encoding="utf-8")
    result = runner.invoke(
        app, ["construir", "--salida", str(foreign), "--descarga", str(snapshot), *DATES]
    )
    assert result.exit_code == 1
    assert "no es una web generada" in result.output
    assert (foreign / "importante.txt").is_file()

    built = tmp_path / "sitio"
    _build(built, snapshot)
    (built / "sobrante.html").write_text("de una versión anterior", encoding="utf-8")
    _build(built, snapshot)  # a website built before is replaced entirely
    assert not (built / "sobrante.html").exists()
