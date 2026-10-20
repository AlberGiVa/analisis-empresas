"""Acceptance: one command loads the sample data, runs the pipeline and writes the reports."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from company_analysis.cli import app

runner = CliRunner()


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ANALYSIS_DB_PATH", str(tmp_path / "analysis.duckdb"))
    monkeypatch.setenv("ANALYSIS_OUTPUT_DIR", str(tmp_path / "output"))
    return tmp_path


def run_directories(workspace: Path) -> list[Path]:
    return sorted((workspace / "output").iterdir())


def test_demo_does_everything_with_one_command(workspace: Path) -> None:
    result = runner.invoke(app, ["demo"])
    assert result.exit_code == 0, result.output
    assert "Datos de ejemplo cargados" in result.output
    assert "a 31/12/2025" in result.output
    assert "a 30/06/2026" in result.output
    (run_dir,) = run_directories(workspace)
    assert (run_dir / "ranking.html").is_file()
    assert (run_dir / "ranking.csv").is_file()
    assert len(list((run_dir / "fichas").glob("*.html"))) == 20


def test_notes_appear_in_the_regenerated_fichas(workspace: Path) -> None:
    assert runner.invoke(app, ["demo"]).exit_code == 0
    added = runner.invoke(
        app,
        ["nota", "nueva", "vald", "Tesis: <b>mejora</b> de márgenes", "--decision", "seguimiento",
         "--autor", "Ana", "--fecha", "2026-07-01"],
    )  # fmt: skip
    assert added.exit_code == 0, added.output
    assert "Nota guardada para VALD" in added.output
    listed = runner.invoke(app, ["nota", "listar", "VALD"])
    assert "01/07/2026 · VALD · Ana · En seguimiento" in listed.output
    regenerated = runner.invoke(app, ["fichas"])
    assert regenerated.exit_code == 0, regenerated.output
    (run_dir,) = run_directories(workspace)
    ficha = (run_dir / "fichas" / "VALD.html").read_text(encoding="utf-8")
    assert "Tesis: &lt;b&gt;mejora&lt;/b&gt; de márgenes" in ficha  # escaped, never run as HTML


def test_note_for_an_unknown_company_is_rejected(workspace: Path) -> None:
    assert runner.invoke(app, ["cargar"]).exit_code == 0
    result = runner.invoke(app, ["nota", "nueva", "NOPE", "texto"])
    assert result.exit_code == 1
    assert "No hay ninguna empresa" in result.output


def test_fichas_without_runs_is_explained(workspace: Path) -> None:
    assert runner.invoke(app, ["cargar"]).exit_code == 0
    result = runner.invoke(app, ["fichas"])
    assert result.exit_code == 1
    assert "no hay ejecuciones completadas" in result.output.lower()


def test_real_data_are_imported_from_an_excel_workbook(workspace: Path) -> None:
    example = workspace / "ejemplo.xlsx"
    created = runner.invoke(app, ["plantilla", str(example), "--ejemplo"])
    assert created.exit_code == 0, created.output
    imported = runner.invoke(app, ["importar", str(example)])
    assert imported.exit_code == 0, imported.output
    assert "20 emisores" in imported.output
    again = runner.invoke(app, ["importar", str(example)])
    assert "ya estaban cargados" in again.output
    assert runner.invoke(app, ["ejecutar", "--fecha", "2026-06-30"]).exit_code == 0


def test_an_invalid_workbook_loads_nothing(workspace: Path) -> None:
    template = workspace / "plantilla.xlsx"
    assert runner.invoke(app, ["plantilla", str(template)]).exit_code == 0
    result = runner.invoke(app, ["importar", str(template)])
    assert result.exit_code == 1
    assert "No se ha cargado nada" in result.output
    assert not (workspace / "analysis.duckdb").exists()
