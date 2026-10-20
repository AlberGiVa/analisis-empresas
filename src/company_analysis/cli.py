"""Command line interface. Command names, help and messages are in Spanish (user interface)."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from typing import Annotated, NoReturn

import duckdb
import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from company_analysis import __version__
from company_analysis.config import ScoreType
from company_analysis.config_loader import ConfigError, LoadedConfig, load_config
from company_analysis.formatting import format_date
from company_analysis.pipeline import AnalysisError, RunOutcome, run_analysis
from company_analysis.providers import PROVIDERS, create_provider
from company_analysis.settings import Settings
from company_analysis.storage import latest_price_date, open_database, save_bundle
from company_analysis.storage.runs import list_runs

app = typer.Typer(
    name="analisis",
    help="Análisis de empresas del fondo multiactivos: métricas, puntuaciones, alertas y fichas.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()

COLLECTION_LABELS = {
    "issuers": "emisores",
    "equities": "acciones",
    "bonds": "bonos",
    "financial_facts": "datos financieros",
    "equity_prices": "cotizaciones de acciones",
    "bond_quotes": "cotizaciones de bonos",
    "ratings": "ratings",
    "fx_rates": "tipos de cambio",
}


def fail(message: str) -> NoReturn:
    """Show an error message (without a traceback) and end with exit code 1."""
    typer.secho(message, err=True, fg=typer.colors.RED)
    raise typer.Exit(code=1)


@contextmanager
def database(settings: Settings, *, read_only: bool = False) -> Iterator[duckdb.DuckDBPyConnection]:
    """Open the local database, explaining the usual problems in plain words."""
    if read_only and not settings.db_path.exists():
        fail(f"Todavía no hay base de datos en {settings.db_path}. Ejecuta antes 'cargar'.")
    try:
        with open_database(settings.db_path, read_only=read_only) as conn:
            yield conn
    except duckdb.IOException as error:
        fail(
            f"No se puede abrir la base de datos {settings.db_path}. Puede estar abierta en otro "
            f"programa (por ejemplo, el panel); ciérralo y vuelve a intentarlo.\nDetalle: {error}"
        )


def methodology(settings: Settings) -> LoadedConfig:
    try:
        return load_config(settings.config_path)
    except ConfigError as error:
        fail(str(error))


def parse_date(text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError:
        fail(f"Fecha no válida: {text!r}. Usa el formato AAAA-MM-DD (por ejemplo, 2026-06-30).")


def analyse(conn: duckdb.DuckDBPyConnection, as_of: date, config: LoadedConfig) -> RunOutcome:
    try:
        return run_analysis(conn, as_of=as_of, config=config)
    except AnalysisError as error:
        fail(f"La ejecución no se ha completado (queda registrada como fallida): {error}")


def print_run(outcome: RunOutcome) -> None:
    record = outcome.record
    shown = {
        score_type: sum(1 for s in outcome.scores if s.score_type is score_type and s.displayed)
        for score_type in ScoreType
    }
    commit = f", commit {record.git_commit}" if record.git_commit else ""
    console.print(f"[bold]Ejecución {record.run_id}[/bold] a {format_date(record.as_of_date)}")
    console.print(
        f"  Configuración {record.config_version} (huella {record.config_hash[:8]}); "
        f"código {record.code_version}{commit}"
    )
    console.print(
        f"  {len(outcome.snapshots)} empresas. Con puntuación: "
        f"renta variable {shown[ScoreType.EQUITY]}, crédito {shown[ScoreType.CREDIT]}."
    )
    console.print(f"  Alertas: {len(outcome.alerts)}")
    for alert in outcome.alerts:
        console.print(f"   - {alert.issuer_id} · {alert.rule.label}: {alert.message}")


@app.callback()
def main() -> None:
    """Análisis de empresas del fondo multiactivos."""


@app.command("version")
def show_version() -> None:
    """Muestra la versión instalada de la herramienta."""
    typer.echo(f"company-analysis {__version__}")


@app.command("cargar")
def load_data(
    proveedor: Annotated[
        str, typer.Option(help=f"Proveedor de datos ({', '.join(PROVIDERS)}).")
    ] = "ejemplo",
) -> None:
    """Carga los datos de un proveedor en la base local, sin sobrescribir ni duplicar nada."""
    settings = Settings()
    if proveedor not in PROVIDERS:
        fail(f"Proveedor desconocido: {proveedor!r}. Disponibles: {', '.join(PROVIDERS)}.")
    provider = create_provider(proveedor, settings)
    try:
        bundle = provider.fetch()
    except ValidationError as error:
        fail(f"Los datos del proveedor '{proveedor}' no son válidos:\n{error}")
    with database(settings) as conn:
        result = save_bundle(conn, bundle, provider.name)
    batch = result.batch
    counts = ", ".join(
        f"{count} {COLLECTION_LABELS[name]}" for name, count in batch.row_counts.items()
    )
    if result.created:
        typer.echo(f"Cargado el lote {batch.load_id}: {counts}.")
    else:
        typer.echo(
            f"Estos datos ya estaban cargados (lote {batch.load_id}, "
            f"{batch.loaded_at:%d/%m/%Y %H:%M} UTC); no se ha duplicado nada."
        )


@app.command("ejecutar")
def run_command(
    fecha: Annotated[
        str | None,
        typer.Option(
            "--fecha",
            help="Fecha de análisis (AAAA-MM-DD). Por defecto, la última con cotizaciones.",
        ),
    ] = None,
) -> None:
    """Calcula métricas, puntuaciones, filtros y alertas a una fecha y registra la ejecución."""
    settings = Settings()
    config = methodology(settings)
    with database(settings) as conn:
        as_of = parse_date(fecha) if fecha else latest_price_date(conn)
        if as_of is None:
            fail("No hay cotizaciones cargadas: ejecuta antes 'cargar'.")
        outcome = analyse(conn, as_of, config)
    print_run(outcome)


@app.command("ejecuciones")
def list_runs_command() -> None:
    """Muestra el registro de ejecuciones: fecha, datos usados, configuración y código."""
    settings = Settings()
    with database(settings, read_only=True) as conn:
        runs = list_runs(conn)
    if not runs:
        typer.echo("Todavía no hay ejecuciones.")
        return
    table = Table("Ejecución", "Fecha de análisis", "Inicio (UTC)", "Estado", "Configuración",
                  "Código", "Lotes", "Usuario", title="Ejecuciones registradas")  # fmt: skip
    for run in runs:
        table.add_row(
            run.run_id,
            format_date(run.as_of_date),
            f"{run.started_at:%d/%m/%Y %H:%M}",
            run.status.label if run.error is None else f"{run.status.label}: {run.error}",
            f"{run.config_version} ({run.config_hash[:8]})",
            f"{run.code_version} {run.git_commit or ''}".strip(),
            str(len(run.load_ids)),
            run.triggered_by,
        )
    console.print(table)
