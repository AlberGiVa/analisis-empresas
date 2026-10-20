"""Command line interface. Command names, help and messages are in Spanish (user interface)."""

import typer

from company_analysis import __version__

app = typer.Typer(
    name="analisis",
    help="Análisis de empresas del fondo multiactivos: métricas, puntuaciones, alertas y fichas.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def main() -> None:
    """Análisis de empresas del fondo multiactivos."""


@app.command("version")
def show_version() -> None:
    """Muestra la versión instalada de la herramienta."""
    typer.echo(f"company-analysis {__version__}")
