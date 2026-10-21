"""Study with real data from public sources, isolated from the rest of the tool.

Everything lives under ``estudio-real/``: universe, methodology, downloads, database and outputs.
The paths are fixed here, not taken from the environment, so a study command can never write to
the main database. Real data (``datos/``, ``salida/``) are ignored by git.

Run it with ``estudio-real\\estudio.cmd <comando>`` (Spanish CLI).
"""

import json
import os
import subprocess
import webbrowser
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Annotated

import duckdb
import typer
from rich.console import Console
from rich.table import Table

from company_analysis.cli import (
    _wait_for_port,
    analyse,
    fail,
    panel_command_line,
    parse_date,
    print_run,
)
from company_analysis.clock import local_today, utc_now
from company_analysis.config_loader import ConfigError, LoadedConfig, load_config
from company_analysis.formatting import format_date
from company_analysis.providers.public.downloads import (
    Request,
    download,
    esef_reports,
    latest_snapshot,
    plan,
)
from company_analysis.providers.public.provider import (
    PublicDataProvider,
    PublicDataResult,
    SnapshotError,
)
from company_analysis.providers.public.universe import UniverseError, load_universe
from company_analysis.reports import ReportError, build_run_view, write_reports
from company_analysis.reports.study import build_study_view, write_study_report
from company_analysis.settings import Settings
from company_analysis.storage import open_database, save_bundle
from company_analysis.storage.runs import latest_completed_run, list_runs

app = typer.Typer(
    name="estudio",
    help="Estudio con datos reales de fuentes públicas, aislado del resto de la herramienta.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


@dataclass(frozen=True)
class StudyPaths:
    root: Path

    @property
    def universe(self) -> Path:
        return self.root / "universo.yaml"

    @property
    def methodology(self) -> Path:
        return self.root / "metodologia.yaml"

    @property
    def data(self) -> Path:
        return self.root / "datos"

    @property
    def downloads(self) -> Path:
        return self.data / "crudo"

    @property
    def database(self) -> Path:
        return self.data / "estudio.duckdb"

    @property
    def last_load(self) -> Path:
        return self.data / "ultima-carga.json"

    @property
    def output(self) -> Path:
        return self.root / "salida"

    def settings(self) -> Settings:
        """Main settings with every path pointing inside the study (never the main database)."""
        return Settings(db_path=self.database, output_dir=self.output, config_path=self.methodology)

    def environment(self) -> dict[str, str]:
        """Environment for child processes (the panel) with the study paths."""
        return {
            **os.environ,
            "ANALYSIS_DB_PATH": str(self.database),
            "ANALYSIS_OUTPUT_DIR": str(self.output),
            "ANALYSIS_CONFIG_PATH": str(self.methodology),
        }


def study_paths() -> StudyPaths:
    return StudyPaths(Settings().study_dir)


@contextmanager
def study_database(
    paths: StudyPaths, *, read_only: bool = False
) -> Iterator[duckdb.DuckDBPyConnection]:
    if read_only and not paths.database.exists():
        fail("El estudio todavía no tiene datos: ejecuta antes 'descargar' y 'cargar' (o 'todo').")
    paths.data.mkdir(parents=True, exist_ok=True)
    with open_database(paths.database, read_only=read_only) as conn:
        yield conn


def study_methodology(paths: StudyPaths) -> LoadedConfig:
    try:
        return load_config(paths.methodology)
    except ConfigError as error:
        fail(str(error))


def comparison_date(today: date) -> date:
    """End of the previous half-year (30 June or 31 December), the default comparison date."""
    if (today.month, today.day) > (6, 30):
        return date(today.year, 6, 30)
    return date(today.year - 1, 12, 31)


# --- Commands ------------------------------------------------------------------------------------
@app.command("descargar")
def download_command() -> None:
    """Descarga los datos públicos del universo en una carpeta nueva con fecha (no borra nada)."""
    paths = study_paths()
    try:
        universe = load_universe(paths.universe)
    except UniverseError as error:
        fail(str(error))
    today = local_today()
    requests = plan(universe, today)
    console.print(
        f"Descargando {len(requests)} ficheros de {len(universe.companies)} empresas "
        "(SEC, informes anuales europeos, Nasdaq, Yahoo Finance y BCE)…"
    )

    def progress(request: Request) -> None:
        console.print(f"  {request.path}", style="dim")

    snapshot = download(
        requests,
        paths.downloads,
        sec_agent=Settings().http_user_agent,
        progress=progress,
        then=esef_reports(universe, comparison_date(today)),
    )
    console.print(f"Descarga guardada en {snapshot.folder} ({len(snapshot.files)} ficheros).")
    for failure in snapshot.failures:
        kind = "OBLIGATORIO" if failure.required else "opcional"
        console.print(
            f"  [yellow]No se ha podido descargar ({kind}):[/yellow] "
            f"{failure.path}: {failure.error}"
        )
    if not snapshot.complete:
        fail("Faltan ficheros obligatorios: vuelve a intentarlo más tarde. No se ha cargado nada.")


def _build(paths: StudyPaths, snapshot: Path) -> PublicDataResult:
    try:
        return PublicDataProvider(paths.universe, snapshot).build()
    except (UniverseError, SnapshotError) as error:
        fail(str(error))
    except ValueError as error:  # the bundle did not pass validation
        fail(f"Los datos descargados no son válidos:\n{error}")


@app.command("cargar")
def load_command() -> None:
    """Valida la última descarga y la carga en la base del estudio (solo inserción)."""
    paths = study_paths()
    snapshot = latest_snapshot(paths.downloads)
    if snapshot is None:
        fail("No hay ninguna descarga: ejecuta antes 'descargar'.")
    result = _build(paths, snapshot)
    with study_database(paths) as conn:
        loaded = save_bundle(conn, result.bundle, PublicDataProvider.name)
    paths.last_load.write_text(
        json.dumps(
            {
                "descarga": snapshot.name,
                "lote": loaded.batch.load_id,
                "cargado": utc_now().isoformat(timespec="seconds"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    counts = result.bundle.row_counts()
    state = "Cargado el lote" if loaded.created else "Ya estaba cargado el lote"
    console.print(
        f"{state} {loaded.batch.load_id} desde la descarga {snapshot.name}: "
        f"{counts['issuers']} empresas, {counts['financial_facts']} datos financieros, "
        f"{counts['equity_prices']} cotizaciones y {counts['fx_rates']} tipos de cambio."
    )
    warnings = [(q.issuer_id, w) for q in result.companies for w in q.warnings]
    if warnings:
        console.print(
            f"[yellow]{len(warnings)} avisos de calidad de datos[/yellow] (detalle en el informe):"
        )
        for issuer_id, warning in warnings:
            console.print(f"  {issuer_id}: {warning}")


@app.command("ejecutar")
def run_command(
    fecha: Annotated[
        list[str] | None,
        typer.Option(
            help="Fecha de análisis AAAA-MM-DD (se puede repetir). Por defecto, el cierre del "
            "semestre anterior y hoy."
        ),
    ] = None,
) -> None:
    """Analiza el universo a una o varias fechas con la metodología del estudio."""
    paths = study_paths()
    today = local_today()
    dates = (
        sorted({parse_date(text) for text in fecha}) if fecha else [comparison_date(today), today]
    )
    config = study_methodology(paths)
    with study_database(paths) as conn:
        for as_of in dates:
            print_run(analyse(conn, as_of, config))


def _data_of_last_load(paths: StudyPaths) -> PublicDataResult | None:
    if not paths.last_load.is_file():
        return None
    record = json.loads(paths.last_load.read_text(encoding="utf-8"))
    snapshot = paths.downloads / str(record.get("descarga", ""))
    return _build(paths, snapshot) if snapshot.is_dir() else None


@app.command("informe")
def report_command() -> None:
    """Genera el informe del estudio, el ranking y las fichas de la última ejecución."""
    paths = study_paths()
    universe = load_universe(paths.universe)
    with study_database(paths, read_only=True) as conn:
        latest = latest_completed_run(conn)
        if latest is None:
            fail("No hay ejecuciones: ejecuta antes 'ejecutar'.")
        earlier = latest_completed_run(conn, before_as_of=latest.as_of_date)
        try:
            view = build_run_view(conn, latest.run_id)
            previous = build_run_view(conn, earlier.run_id) if earlier else None
        except ReportError as error:
            fail(str(error))
        files = write_reports(view, paths.output)
        study = build_study_view(
            conn,
            view,
            previous,
            _data_of_last_load(paths),
            title=universe.name,
            description=universe.description,
        )
    report = write_study_report(study, files.directory)
    console.print(f"[bold]Informe del estudio:[/bold] {report}")
    console.print(f"  Ranking: {files.ranking_html}")
    console.print(f"  Fichas ({len(files.fichas)}): {files.directory / 'fichas'}")


@app.command("todo")
def all_command() -> None:
    """Descarga, carga, analiza a dos fechas y genera el informe."""
    download_command()
    load_command()
    run_command(None)
    report_command()


@app.command("ejecuciones")
def runs_command() -> None:
    """Lista las ejecuciones del estudio."""
    paths = study_paths()
    with study_database(paths, read_only=True) as conn:
        runs = list_runs(conn)
    table = Table(title="Ejecuciones del estudio")
    for column in ("Ejecución", "Fecha de análisis", "Estado", "Metodología", "Código"):
        table.add_column(column)
    for run in runs:
        table.add_row(
            run.run_id,
            format_date(run.as_of_date),
            run.status.label,
            run.config_version,
            f"{run.code_version} {run.git_commit or ''}".strip(),
        )
    console.print(table)


@app.command("panel")
def panel_command(
    puerto: Annotated[int, typer.Option(help="Puerto local del panel.")] = 8502,
) -> None:
    """Abre el panel con los datos del estudio (solo en este equipo). Ciérralo con Ctrl+C."""
    paths = study_paths()
    if not paths.database.exists():
        fail("El estudio todavía no tiene datos: ejecuta antes 'todo'.")
    url = f"http://localhost:{puerto}"
    console.print(f"Abriendo el panel del estudio en {url} (Ctrl+C para cerrarlo)…")
    settings = paths.settings()
    process = subprocess.Popen(
        panel_command_line(puerto), cwd=settings.project_root, env=paths.environment()
    )
    try:
        if _wait_for_port(puerto, timeout=60):
            webbrowser.open(url)
        process.wait()
    except KeyboardInterrupt:
        process.terminate()


if __name__ == "__main__":
    app()
