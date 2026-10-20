"""The public website, built end to end from a synthetic download without prices (no network)."""

import re
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from company_analysis.settings import PROJECT_ROOT, Settings
from company_analysis.web import WebError, app, load_news
from tests import public_samples

runner = CliRunner()
DATES = ["--fecha", "2026-06-30", "--fecha", "2026-08-14"]
LINK = re.compile(r'(?:href|src)="([^"]+)"')


def _study(root: Path, *, prices: bool) -> Path:
    """A study folder like ``estudio-real/`` with a synthetic download; returns the download."""
    shutil.copy(PROJECT_ROOT / "estudio-real" / "metodologia-web.yaml", root)
    public_samples.write_universe(root)
    return public_samples.write_snapshot(root / "descarga", prices=prices)


def _build(target: Path, snapshot: Path) -> str:
    result = runner.invoke(
        app, ["construir", "--salida", str(target), "--descarga", str(snapshot), *DATES]
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
        _build(target, snapshot)
        assert main_database.exists() == existed  # the main database is never touched
    assert not (root / "datos").exists()  # nor the study's
    return target


def _pages(site: Path) -> list[Path]:
    return sorted(site.rglob("*.html"))


def test_every_section_is_built(site: Path) -> None:
    for page in (
        "index.html",
        "reales/index.html",
        "reales/ranking.html",
        "reales/ranking.csv",
        "reales/fichas/ZZAA.html",
        "ejemplo/ranking.html",
        "ejemplo/ranking.csv",
        "como-funciona.html",
        "novedades.html",
        ".nojekyll",
        "marca/luceiro-logo.webp",
        "presentacion.html",
    ):
        assert (site / page).is_file(), page
    assert len(list((site / "ejemplo" / "fichas").glob("*.html"))) == 20
    home = (site / "index.html").read_text(encoding="utf-8")
    assert "Universo de prueba" in home
    assert 'href="reales/index.html"' in home


def test_every_page_has_the_navigation_and_working_links(site: Path) -> None:
    for page in _pages(site):
        html = page.read_text(encoding="utf-8")
        assert 'aria-label="Secciones"' in html, page
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


def test_news_are_read_newest_first_and_checked(tmp_path: Path) -> None:
    path = tmp_path / "novedades.yaml"
    path.write_text(
        '- {fecha: "2026-01-02", titulo: Antigua, texto: "Uno."}\n'
        "- {fecha: 2026-03-04, titulo: Nueva, texto: 'Dos  y\n  tres.', enlace: index.html}\n",
        encoding="utf-8",
    )
    news = load_news(path)
    assert [entry.title for entry in news] == ["Nueva", "Antigua"]
    assert news[0].text == "Dos y tres."
    assert news[0].day_text == "04/03/2026"

    path.write_text(
        '- {fecha: "2026-01-02", titulo: X, texto: Y, enlace: otra.html}\n', encoding="utf-8"
    )
    with pytest.raises(WebError, match="no es una página de la web"):
        load_news(path)
    path.write_text("- {titulo: X, texto: Y}\n", encoding="utf-8")
    with pytest.raises(WebError, match="fecha"):
        load_news(path)


def test_the_published_news_file_is_valid() -> None:
    assert load_news(PROJECT_ROOT / "docs" / "novedades.yaml")
