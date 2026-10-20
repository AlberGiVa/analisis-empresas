from typer.testing import CliRunner

from company_analysis import __version__
from company_analysis.cli import app

runner = CliRunner()


def test_version_command_prints_the_installed_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_running_without_arguments_shows_help() -> None:
    result = runner.invoke(app, [])
    assert "Análisis de empresas" in result.output
