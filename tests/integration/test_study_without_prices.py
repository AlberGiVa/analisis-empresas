"""The study on a download without share prices (the sources the public website may republish)."""

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from company_analysis.settings import PROJECT_ROOT
from company_analysis.study import app
from tests import public_samples

runner = CliRunner()


@pytest.fixture
def study(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ANALYSIS_STUDY_DIR", str(tmp_path))
    shutil.copy(
        PROJECT_ROOT / "estudio-real" / "metodologia-web.yaml", tmp_path / "metodologia.yaml"
    )
    public_samples.write_universe(tmp_path)
    public_samples.write_snapshot(tmp_path / "datos" / "crudo" / "20260815T080000Z", prices=False)
    return tmp_path


def test_the_report_without_prices_never_mentions_them(study: Path) -> None:
    loaded = runner.invoke(app, ["cargar"])
    assert loaded.exit_code == 0, loaded.output
    # Without prices there is no latest quote to date the runs: explicit dates.
    ran = runner.invoke(app, ["ejecutar", "--fecha", "2026-06-30", "--fecha", "2026-08-14"])
    assert ran.exit_code == 0, ran.output
    report = runner.invoke(app, ["informe"])
    assert report.exit_code == 0, report.output

    (path,) = (study / "salida").glob("*/estudio.html")
    html = path.read_text(encoding="utf-8")
    assert "Zeta Foods Inc." in html
    assert "2026.10-web-2" in html  # the methodology without valuation factors
    assert "sin cotizaciones" in html
    assert "Rentabilidad frente a apalancamiento" in html
    assert "Valoración frente a apalancamiento" not in html
    assert "Nasdaq" not in html
    assert "Yahoo" not in html
    for header in ("Capitaliz.", "EV/EBITDA", "PER", "FCF yield"):
        assert f">{header}</th>" not in html
    for header in ("ROIC", "Margen EBITDA", "DN/EBITDA"):
        assert f">{header}</th>" in html
    assert "Qué ha cambiado desde el 30/06/2026" in html
    assert (path.parent / "fichas" / "ZZAA.html").is_file()
