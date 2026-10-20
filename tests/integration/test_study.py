"""The isolated real-data study, end to end on a synthetic snapshot (no network)."""

import shutil
from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

from company_analysis.settings import PROJECT_ROOT, Settings
from company_analysis.study import app, comparison_date
from tests import public_samples

runner = CliRunner()


@pytest.fixture
def study(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ANALYSIS_STUDY_DIR", str(tmp_path))
    shutil.copy(PROJECT_ROOT / "estudio-real" / "metodologia.yaml", tmp_path / "metodologia.yaml")
    public_samples.write_universe(tmp_path)
    public_samples.write_snapshot(tmp_path / "datos" / "crudo" / "20260815T080000Z")
    return tmp_path


def test_load_run_and_report_inside_the_study_folder(study: Path) -> None:
    loaded = runner.invoke(app, ["cargar"])
    assert loaded.exit_code == 0, loaded.output
    assert "Cargado el lote" in loaded.output
    assert "avisos de calidad" in loaded.output
    again = runner.invoke(app, ["cargar"])
    assert "Ya estaba cargado" in again.output

    ran = runner.invoke(app, ["ejecutar", "--fecha", "2026-06-30", "--fecha", "2026-08-14"])
    assert ran.exit_code == 0, ran.output

    report = runner.invoke(app, ["informe"])
    assert report.exit_code == 0, report.output
    (path,) = (study / "salida").glob("*/estudio.html")
    html = path.read_text(encoding="utf-8")
    assert "Zeta Foods Inc." in html
    assert "Qué ha cambiado desde el 30/06/2026" in html
    assert "Resultado operativo atípico" in html
    assert (path.parent / "ranking.html").is_file()
    assert (study / "datos" / "estudio.duckdb").is_file()


def test_the_study_never_uses_the_main_database(study: Path) -> None:
    main = Settings().db_path
    existed = main.exists()
    assert runner.invoke(app, ["cargar"]).exit_code == 0
    assert main.exists() == existed
    assert (study / "datos" / "estudio.duckdb").is_file()


def test_report_without_runs_explains_what_to_do(study: Path) -> None:
    assert runner.invoke(app, ["cargar"]).exit_code == 0
    result = runner.invoke(app, ["informe"])
    assert result.exit_code == 1
    assert "ejecutar" in result.output


def test_load_without_a_download_explains_what_to_do(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANALYSIS_STUDY_DIR", str(tmp_path))
    public_samples.write_universe(tmp_path)
    result = runner.invoke(app, ["cargar"])
    assert result.exit_code == 1
    assert "descargar" in result.output


@pytest.mark.parametrize(
    ("today", "expected"),
    [("2026-10-20", "2026-06-30"), ("2026-06-30", "2025-12-31"), ("2026-03-01", "2025-12-31")],
)
def test_default_comparison_date_is_the_previous_half_year_end(today: str, expected: str) -> None:
    assert comparison_date(date.fromisoformat(today)) == date.fromisoformat(expected)
