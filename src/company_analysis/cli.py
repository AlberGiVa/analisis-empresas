"""Command line interface. Command names, help and messages are in Spanish (user interface)."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, NoReturn

import duckdb
import typer
from pydantic import ValidationError

from company_analysis import __version__
from company_analysis.providers import PROVIDERS, create_provider
from company_analysis.settings import Settings
from company_analysis.storage import open_database, save_bundle

app = typer.Typer(
    name="analisis",
    help="Análisis de empresas del fondo multiactivos: métricas, puntuaciones, alertas y fichas.",
    no_args_is_help=True,
    add_completion=False,
)

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
