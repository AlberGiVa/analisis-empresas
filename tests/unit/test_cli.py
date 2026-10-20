from pathlib import Path

import pytest
from typer.testing import CliRunner

from company_analysis import __version__
from company_analysis.cli import app

runner = CliRunner()


@pytest.fixture
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "analysis.duckdb"
    monkeypatch.setenv("ANALYSIS_DB_PATH", str(db_path))
    return db_path


def test_version_command_prints_the_installed_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_running_without_arguments_shows_help() -> None:
    result = runner.invoke(app, [])
    assert "Análisis de empresas" in result.output


def test_load_command_is_idempotent(isolated_db: Path) -> None:
    first = runner.invoke(app, ["cargar"])
    assert first.exit_code == 0, first.output
    assert "20 emisores" in first.output
    second = runner.invoke(app, ["cargar"])
    assert second.exit_code == 0
    assert "ya estaban cargados" in second.output
    assert isolated_db.exists()


def test_unknown_provider_is_reported_without_traceback(isolated_db: Path) -> None:
    result = runner.invoke(app, ["cargar", "--proveedor", "bloomberg"])
    assert result.exit_code == 1
    assert "Proveedor desconocido" in result.output
