"""Command line interface. Command names, help and messages are in Spanish (user interface)."""

import socket
import subprocess
import sys
import time
import webbrowser
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from enum import StrEnum
from typing import Annotated, NoReturn

import duckdb
import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from company_analysis import __version__
from company_analysis.app import DASHBOARD
from company_analysis.clock import local_today
from company_analysis.config import ScoreType
from company_analysis.config_loader import ConfigError, LoadedConfig, load_config
from company_analysis.formatting import format_date
from company_analysis.journal import Decision, JournalError, add_entry, list_entries
from company_analysis.pipeline import AnalysisError, RunOutcome, run_analysis
from company_analysis.provenance import current_user
from company_analysis.providers import PROVIDERS, create_provider
from company_analysis.providers.sample_generator import DEMO_AS_OF_DATES
from company_analysis.reports import ReportError, ReportFiles, build_run_view, write_reports
from company_analysis.settings import Settings
from company_analysis.storage import latest_price_date, open_database, save_bundle
from company_analysis.storage.runs import latest_completed_run, list_runs

app = typer.Typer(
    name="analisis",
    help="Análisis de empresas del fondo multiactivos: métricas, puntuaciones, alertas y fichas.",
    no_args_is_help=True,
    add_completion=False,
)
note_app = typer.Typer(
    help="Diario del analista: tesis de inversión y notas por empresa.", no_args_is_help=True
)
app.add_typer(note_app, name="nota")
console = Console(soft_wrap=True)  # long paths are never broken across lines

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


class DecisionOption(StrEnum):
    """Decisions as typed in the command line (Spanish)."""

    NINGUNA = "ninguna"
    SEGUIMIENTO = "seguimiento"
    INVERTIR = "invertir"
    MANTENER = "mantener"
    REDUCIR = "reducir"
    DESINVERTIR = "desinvertir"


_DECISIONS = {
    DecisionOption.NINGUNA: Decision.NONE,
    DecisionOption.SEGUIMIENTO: Decision.WATCH,
    DecisionOption.INVERTIR: Decision.INVEST,
    DecisionOption.MANTENER: Decision.HOLD,
    DecisionOption.REDUCIR: Decision.REDUCE,
    DecisionOption.DESINVERTIR: Decision.DIVEST,
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


def generate_reports(
    conn: duckdb.DuckDBPyConnection, run_id: str, settings: Settings
) -> ReportFiles:
    try:
        view = build_run_view(conn, run_id)
    except ReportError as error:
        fail(str(error))
    return write_reports(view, settings.output_dir)


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


def print_reports(files: ReportFiles) -> None:
    console.print(f"  Ranking: {files.ranking_html}")
    console.print(f"  Ranking para Excel: {files.ranking_csv}")
    console.print(f"  Fichas ({len(files.fichas)}): {files.directory / 'fichas'}")


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


@app.command("fichas")
def reports_command(
    ejecucion: Annotated[
        str | None,
        typer.Option(
            "--ejecucion", help="Identificador de la ejecución. Por defecto, la última completada."
        ),
    ] = None,
) -> None:
    """Genera el ranking (HTML y CSV para Excel) y una ficha HTML por empresa."""
    settings = Settings()
    with database(settings) as conn:
        run_id = ejecucion or latest_run_id(conn)
        files = generate_reports(conn, run_id, settings)
    console.print(f"Informes de la ejecución {run_id}:")
    print_reports(files)


def latest_run_id(conn: duckdb.DuckDBPyConnection) -> str:
    latest = latest_completed_run(conn)
    if latest is None:
        fail("Todavía no hay ejecuciones completadas: ejecuta antes 'ejecutar'.")
    return latest.run_id


@app.command("demo")
def demo_command() -> None:
    """Todo de una vez con los datos de ejemplo: carga, análisis a dos fechas, ranking y fichas."""
    settings = Settings()
    config = methodology(settings)
    provider = create_provider("ejemplo", settings)
    bundle = provider.fetch()
    with database(settings) as conn:
        loaded = save_bundle(conn, bundle, provider.name)
        state = "cargados" if loaded.created else "ya estaban cargados"
        console.print(f"Datos de ejemplo {state} (lote {loaded.batch.load_id}).")
        outcomes = [analyse(conn, as_of, config) for as_of in DEMO_AS_OF_DATES]
        files = generate_reports(conn, outcomes[-1].record.run_id, settings)
    for outcome in outcomes:
        print_run(outcome)
    console.print("[bold]Informes de la última ejecución[/bold]")
    print_reports(files)
    console.print("Para abrir el panel: .\\analisis panel")


@note_app.command("nueva")
def new_note(
    empresa: Annotated[
        str, typer.Argument(help="Identificador de la empresa (por ejemplo, VALD).")
    ],
    texto: Annotated[str, typer.Argument(help="Texto de la nota, entre comillas.")],
    decision: Annotated[
        DecisionOption, typer.Option(help="Decisión del analista.")
    ] = DecisionOption.NINGUNA,
    autor: Annotated[
        str | None, typer.Option(help="Autor. Por defecto, el usuario del equipo.")
    ] = None,
    fecha: Annotated[
        str | None, typer.Option(help="Fecha de la nota (AAAA-MM-DD). Por defecto, hoy.")
    ] = None,
) -> None:
    """Añade una nota o tesis de inversión al diario (las notas nunca se modifican)."""
    settings = Settings()
    entry_date = parse_date(fecha) if fecha else local_today()
    with database(settings) as conn:
        try:
            entry = add_entry(
                conn,
                issuer_id=empresa.upper(),
                text=texto,
                author=autor or current_user(),
                decision=_DECISIONS[decision],
                entry_date=entry_date,
            )
        except JournalError as error:
            fail(str(error))
    typer.echo(
        f"Nota guardada para {entry.issuer_id} ({format_date(entry.entry_date)}, "
        f"{entry.author}, {entry.decision.label})."
    )


@note_app.command("listar")
def list_notes(
    empresa: Annotated[
        str | None, typer.Argument(help="Identificador de la empresa. Sin él, todas.")
    ] = None,
) -> None:
    """Muestra las notas del diario, de la más reciente a la más antigua."""
    settings = Settings()
    with database(settings) as conn:
        entries = list_entries(conn, empresa.upper() if empresa else None)
    if not entries:
        typer.echo("No hay notas.")
    for entry in entries:
        typer.echo(
            f"{format_date(entry.entry_date)} · {entry.issuer_id} · {entry.author} · "
            f"{entry.decision.label}: {entry.text}"
        )


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


def _wait_for_port(port: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def panel_command_line(port: int) -> list[str]:
    """Streamlit, reachable only from this computer (no network exposure, no external lookups)."""
    return [
        sys.executable, "-m", "streamlit", "run", str(DASHBOARD),
        "--server.address", "localhost", "--server.port", str(port),
        "--server.headless", "true", "--browser.gatherUsageStats", "false",
    ]  # fmt: skip


@app.command("panel")
def panel_command(
    puerto: Annotated[int, typer.Option(help="Puerto local del panel.")] = 8501,
    navegador: Annotated[bool, typer.Option(help="Abrir el navegador automáticamente.")] = True,
) -> None:
    """Abre el panel con el ranking y el detalle de cada empresa. Ciérralo con Ctrl+C."""
    settings = Settings()
    if not settings.db_path.exists():
        fail("Todavía no hay datos: ejecuta antes 'demo' (o 'cargar' y 'ejecutar').")
    url = f"http://localhost:{puerto}"
    typer.echo(f"Abriendo el panel en {url} (Ctrl+C para cerrarlo)…")
    process = subprocess.Popen(panel_command_line(puerto), cwd=settings.project_root)
    try:
        if navegador and _wait_for_port(puerto, timeout=60):
            webbrowser.open(url)
        process.wait()
    except KeyboardInterrupt:
        process.terminate()
