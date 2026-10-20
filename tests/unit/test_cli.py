from pathlib import Path

import pytest
from typer.testing import CliRunner

from company_analysis import __version__
from company_analysis.cli import app, panel_command_line
from company_analysis.settings import PROJECT_ROOT

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


def test_run_at_a_date_and_list_the_runs(isolated_db: Path) -> None:
    assert runner.invoke(app, ["cargar"]).exit_code == 0
    result = runner.invoke(app, ["ejecutar", "--fecha", "2026-06-30"])
    assert result.exit_code == 0, result.output
    assert "a 30/06/2026" in result.output
    assert "Alertas" in result.output
    listing = runner.invoke(app, ["ejecuciones"])
    assert listing.exit_code == 0, listing.output
    assert "Ejecuciones registradas" in listing.output


def test_run_defaults_to_the_latest_price_date(isolated_db: Path) -> None:
    assert runner.invoke(app, ["cargar"]).exit_code == 0
    result = runner.invoke(app, ["ejecutar"])
    assert result.exit_code == 0, result.output
    assert "a 26/06/2026" in result.output  # last weekly close of the sample data


def test_run_errors_are_explained(isolated_db: Path) -> None:
    no_data = runner.invoke(app, ["ejecutar"])
    assert no_data.exit_code == 1
    assert "No hay cotizaciones cargadas" in no_data.output
    bad_date = runner.invoke(app, ["ejecutar", "--fecha", "30/06/2026"])
    assert bad_date.exit_code == 1
    assert "Fecha no válida" in bad_date.output


def test_panel_is_only_reachable_from_this_computer() -> None:
    """Streamlit must not listen on the network nor look up the public IP address."""
    command = panel_command_line(8501)
    assert command[command.index("--server.address") + 1] == "localhost"
    assert command[command.index("--browser.gatherUsageStats") + 1] == "false"
    config = (PROJECT_ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    assert 'address = "localhost"' in config
    assert "gatherUsageStats = false" in config
