"""Public website: the tool's results, open to anyone with the link (GitHub Pages).

A static site with these sections, plus how to read the results:
- the real-data study, only with sources that may be republished (SEC and ECB): no share prices,
  whose terms forbid it, and the methodology of ``estudio-real/metodologia-web.yaml``;
- the sample data (fictitious companies), which show every feature of the tool;
- the showcase page (``docs/muestra-luceiro-capital.html``), published as ``presentacion.html``.

Every page wears the Luceiro Capital identity of the showcase (logo, colours and typefaces).

The analyst's journal is never published. Everything is computed in a temporary folder: building
never touches the main database nor the study's. GitHub Actions builds and publishes it
(``.github/workflows/web.yml``). Decision 0018.

Run it with ``uv run python -m company_analysis.web construir`` (Spanish CLI).
"""

import os
import shutil
import tempfile
import webbrowser
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date
from importlib.resources import files
from pathlib import Path
from typing import Annotated, Any

import duckdb
import typer
from pydantic import ValidationError
from rich.console import Console

from company_analysis.cli import fail, parse_date
from company_analysis.clock import local_now, local_today
from company_analysis.config import ScoreModelConfig
from company_analysis.config_loader import ConfigError, LoadedConfig, load_config
from company_analysis.formatting import format_date
from company_analysis.i18n import CatalogError, Translator, load_catalog, untranslated_report
from company_analysis.metrics import MetricCategory, all_metrics, get_metric
from company_analysis.metrics.base import MetricDefinition
from company_analysis.pipeline import AnalysisError, run_analysis
from company_analysis.provenance import git_commit
from company_analysis.providers import SampleProvider
from company_analysis.providers.public.downloads import download, plan
from company_analysis.providers.public.provider import (
    PublicDataProvider,
    PublicDataResult,
    SnapshotError,
)
from company_analysis.providers.public.universe import UniverseError, load_universe
from company_analysis.providers.sample_generator import DEMO_AS_OF_DATES
from company_analysis.reports import RunView, SiteNav, build_run_view, write_reports
from company_analysis.reports.render import _common_context, environment
from company_analysis.reports.study import StudyView, build_study_view, write_study_report
from company_analysis.reports.views import DISCLAIMER
from company_analysis.settings import Settings
from company_analysis.storage import open_database, save_bundle
from company_analysis.storage.runs import latest_completed_run
from company_analysis.study import comparison_date

app = typer.Typer(
    name="web",
    help="Web pública: ejemplo completo y empresas reales con datos de uso libre (GitHub Pages).",
    no_args_is_help=True,
    add_completion=False,
)
console = Console(soft_wrap=True)

SECTIONS: tuple[tuple[str, str, str], ...] = (  # (key, label, page from the website root)
    ("inicio", "Inicio", "index.html"),
    ("reales", "Empresas reales", "reales/index.html"),
    ("ejemplo", "Casos de ejemplo", "ejemplo/index.html"),
    ("como-funciona", "Cómo funciona", "como-funciona.html"),
    ("presentacion", "Presentación", "presentacion.html"),
    ("configuracion", "Configuración", "configuracion.html"),
)
REAL_NOTICE = (
    "Empresas reales con datos públicos de uso libre: cuentas de la SEC y tipos de cambio del BCE. "
    "Sin cotizaciones, así que no hay capitalización, PER ni EV/EBITDA."
)
SAMPLE_NOTICE = (
    "Casos de ejemplo: empresas ficticias con datos inventados, una por cada caso que la "
    "herramienta sabe tratar. Se comparan con las 20 empresas del ejemplo, aunque solo se "
    "muestran estas."
)
# One fictitious company per case the tool handles (data/sample/README.md):
# (company, case, what to look at)
SAMPLE_CASES: tuple[tuple[str, str, str], ...] = (
    ("VALD", "Empresa sin incidencias", "Todos los datos disponibles: sirve de referencia."),
    ("ORBE", "EBITDA negativo", "PER y EV/EBITDA «no significativos» y alerta de apalancamiento."),
    ("HELV", "Empresa sin deuda", "Sin bonos ni puntuación de crédito; deuda neta negativa."),
    ("CORV", "Falta un dato: inversiones", "FCF yield «sin dato», con el motivo."),
    (
        "LUMB",
        "Falta un dato: gastos financieros",
        "Cobertura de intereses «sin dato», con el motivo.",
    ),
    (
        "SKRV",
        "Cotización desactualizada",
        "Las métricas de mercado quedan como «dato desactualizado».",
    ),
    (
        "NEXL",
        "Reporta en otra divisa",
        "Cotiza en euros y reporta en dólares: se convierte al tipo de cambio.",
    ),
    ("ASHC", "Rebaja de rating", "Alerta de rebaja; su bono pasa al tramo BB."),
    ("VERD", "Subida de rating", "Una subida no genera alerta."),
    (
        "PELL",
        "Ejercicio que no cierra en diciembre",
        "Cierra en marzo y se compara con el año natural.",
    ),
    (
        "GRSH",
        "Tramo de rating con pocos bonos",
        "Diferencial «sin comparables suficientes» y un bono sin rating.",
    ),
    ("BVAL", "Banco", "Las métricas basadas en EBITDA, deuda neta o EV «no aplican»."),
    ("AUBR", "Aseguradora", "Igual que los bancos: esas métricas «no aplican»."),
)
MARKER = ".web-generada"  # marks a folder this command may replace
WEB_METHODOLOGY = "metodologia-web.yaml"
# The showcase page (one self-contained file) is published as is, with a way back to the website.
SHOWCASES = {  # language: (file, sidebar line after which the way back is added, its text)
    "es": (
        Path("docs") / "muestra-luceiro-capital.html",
        '<p class="side-kicker">Análisis de empresas · muestra</p>',
        "← Volver a la web",
    ),
    "en": (
        Path("docs") / "muestra-luceiro-capital.en.html",
        '<p class="side-kicker">Company analysis · showcase</p>',
        "← Back to the website",
    ),
}
LOGO = "luceiro-logo.webp"
ENGLISH = "en"  # folder of the English version
LANGUAGE_LINK = "#cambiar-idioma"  # replaced by the same page in the other language
SWITCH_TO_ENGLISH = (
    '<a class="lang" href="#cambiar-idioma" hreflang="en" lang="en" translate="no">English</a>'
)
SWITCH_TO_SPANISH = (
    '<a class="lang" href="#cambiar-idioma" hreflang="es" lang="es" translate="no">Español</a>'
)


class WebError(Exception):
    """The website cannot be built (the message says why, in Spanish)."""


def nav(active: str, notice: str | None = None) -> SiteNav:
    return SiteNav(links=SECTIONS, active=active, notice=notice)


# --- Sections ------------------------------------------------------------------------------------
def _analyse(conn: duckdb.DuckDBPyConnection, dates: Sequence[date], config: LoadedConfig) -> None:
    for as_of in dates:
        try:
            run_analysis(conn, as_of=as_of, config=config)
        except AnalysisError as error:
            raise WebError(
                f"El análisis a {format_date(as_of)} no se ha completado: {error}"
            ) from error


def _latest_views(conn: duckdb.DuckDBPyConnection) -> tuple[RunView, RunView | None]:
    latest = latest_completed_run(conn)
    if latest is None:
        raise WebError("No se ha completado ningún análisis.")
    earlier = latest_completed_run(conn, before_as_of=latest.as_of_date)
    previous = build_run_view(conn, earlier.run_id) if earlier else None
    return build_run_view(conn, latest.run_id), previous


def build_sample(work: Path, site: Path, settings: Settings) -> RunView:
    """One fictitious company per case, analysed at the demo dates.

    The whole sample is analysed, so that peers, percentiles and rating buckets are those of the
    20 companies; only the companies of ``SAMPLE_CASES`` are shown.
    """
    config = load_config(settings.config_path)
    provider = SampleProvider(settings.sample_data_dir)
    with open_database(work / "ejemplo.duckdb") as conn:
        save_bundle(conn, provider.fetch(), provider.name)
        _analyse(conn, DEMO_AS_OF_DATES, config)
        view, _ = _latest_views(conn)
    shown = {issuer_id for issuer_id, _, _ in SAMPLE_CASES}
    missing = shown - {company.issuer_id for company in view.companies}
    if missing:
        raise WebError(f"Faltan en los datos de ejemplo: {', '.join(sorted(missing))}.")
    cases = replace(view, companies=tuple(c for c in view.companies if c.issuer_id in shown))
    section = nav("ejemplo", SAMPLE_NOTICE)
    write_reports(cases, site, folder="ejemplo", site=section)
    env = environment()
    rows = [(case, cases.company(issuer_id), what) for issuer_id, case, what in SAMPLE_CASES]
    (site / "ejemplo" / "index.html").write_text(
        env.get_template("web_casos.html.j2").render(
            **_common_context(cases, section) | {"site_root": "../"},
            rows=rows,
            total=len(view.companies),
        ),
        encoding="utf-8",
    )
    return cases


PUBLIC_SOURCES = (
    "Cuentas de la SEC (normas contables de EE. UU., sin ajustes) y tipos de cambio del BCE, sin "
    "cotizaciones."
)


def _public_description(description: str) -> str:
    """The universe's description with the sources the website actually uses.

    The sentence about the sources ("Cuentas de la SEC…") is replaced; a description without it
    gets it added. Abbreviations such as "EE. UU." never cut the text.
    """
    head = description.split("Cuentas de la SEC", maxsplit=1)[0].strip()
    return f"{head} {PUBLIC_SOURCES}" if head else PUBLIC_SOURCES


def build_real(
    work: Path,
    site: Path,
    settings: Settings,
    *,
    snapshot: Path | None,
    dates: Sequence[date],
) -> tuple[StudyView, PublicDataResult]:
    """The study's universe with republishable sources only, analysed at ``dates``."""
    study_dir = settings.study_dir
    universe_path = study_dir / "universo.yaml"
    universe = load_universe(universe_path)
    if snapshot is None:
        console.print(
            f"Descargando de la SEC y del BCE las cuentas de {len(universe.companies)} "
            "empresas y los tipos de cambio (sin cotizaciones)…"
        )
        downloaded = download(
            plan(universe, local_today(), prices=False),
            work / "crudo",
            sec_agent=settings.http_user_agent,
        )
        if not downloaded.complete:
            missing = "; ".join(f"{f.path} ({f.error})" for f in downloaded.failures if f.required)
            raise WebError(f"No se han podido descargar ficheros obligatorios: {missing}.")
        snapshot = downloaded.folder
    data = PublicDataProvider(universe_path, snapshot).build()
    # Share prices may never reach the website: their terms do not allow republishing them.
    if data.with_prices or data.bundle.equity_prices:
        raise WebError(
            f"La descarga {snapshot} tiene cotizaciones: la web solo publica fuentes de uso libre. "
            "Usa una descarga sin cotizaciones."
        )
    config = load_config(study_dir / WEB_METHODOLOGY)
    with open_database(work / "reales.duckdb") as conn:
        save_bundle(conn, data.bundle, PublicDataProvider.name)
        _analyse(conn, dates, config)
        view, previous = _latest_views(conn)
        study = build_study_view(
            conn,
            view,
            previous,
            data,
            title=universe.name,
            description=_public_description(universe.description),
        )
    section = nav("reales", REAL_NOTICE)
    write_reports(view, site, folder="reales", site=section)
    write_study_report(study, site / "reales", filename="index.html", site=section)
    return study, data


# --- Pages ---------------------------------------------------------------------------------------
@dataclass(frozen=True)
class FactorText:
    name: str
    weight: str


def _factors(model: ScoreModelConfig) -> list[FactorText]:
    total = sum(factor.weight for factor in model.factors)
    return [
        FactorText(get_metric(f.metric).name, f"{round(f.weight / total * 100)} %")
        for f in model.factors
    ]


def _metric_groups() -> list[tuple[str, list[MetricDefinition]]]:
    metrics = all_metrics()
    return [
        (category.label, [m for m in metrics if m.category is category])
        for category in MetricCategory
    ]


def write_pages(
    site: Path,
    *,
    sample: RunView,
    study: StudyView,
    data: PublicDataResult,
) -> None:
    env = environment()
    common: dict[str, Any] = {
        "site_root": "",
        "generated": f"{local_now():%d/%m/%Y a las %H:%M}",
        "commit": git_commit(),
        "disclaimer": DISCLAIMER,
    }
    real_alerts = [(c, alert) for c in study.run.companies for alert in c.alerts]
    sample_alerts = [(c, alert) for c in sample.companies for alert in c.alerts]
    pages: dict[str, tuple[str, str, dict[str, Any]]] = {  # file: (template, section, context)
        "index.html": (
            "web_inicio.html.j2",
            "inicio",
            {
                "study": study,
                "sample": sample,
                "real_date": format_date(study.run.record.as_of_date),
                "real_previous": (
                    format_date(study.previous.record.as_of_date) if study.previous else None
                ),
                "sample_date": format_date(sample.record.as_of_date),
                "real_alerts": real_alerts,
                "sample_alerts": sample_alerts,
                "quality_warnings": sum(len(q.warnings) for q in data.companies),
                "metrics_count": len(all_metrics()),
            },
        ),
        "como-funciona.html": (
            "web_como_funciona.html.j2",
            "como-funciona",
            {
                "methodologies": [
                    ("Empresas reales", study.run.record.config_version, study.run.config),
                    ("Ejemplo completo", sample.record.config_version, sample.config),
                ],
                "factors": _factors,
                "metric_groups": _metric_groups(),
                "min_peers": sample.config.scoring.min_peers,
            },
        ),
        "configuracion.html": ("web_configuracion.html.j2", "configuracion", {}),
    }
    for filename, (template, key, context) in pages.items():
        (site / filename).write_text(
            env.get_template(template).render(**common, site=nav(key), **context),
            encoding="utf-8",
        )


def write_logo(site: Path) -> None:
    logo = site / "marca" / LOGO
    logo.parent.mkdir()
    logo.write_bytes((files("company_analysis.reports") / "static" / LOGO).read_bytes())


def showcase_page(path: Path, anchor: str, back: str) -> str:
    """The self-contained showcase page, kept from search engines and with a way back."""
    if not path.is_file():
        raise WebError(f"Falta la página de presentación {path}.")
    html = path.read_text(encoding="utf-8")
    if anchor not in html or '<meta charset="utf-8">' not in html:
        raise WebError(f"{path.name} ha cambiado: no se encuentra dónde poner la vuelta a la web.")
    return html.replace(
        '<meta charset="utf-8">',
        '<meta charset="utf-8"><meta name="robots" content="noindex, nofollow">',
        1,
    ).replace(
        anchor,
        f'{anchor}\n    <a href="index.html" style="font-weight:600;text-decoration:none;'
        f'margin-top:-10px">{back}</a>',
        1,
    )


def write_english(site: Path, translator: Translator, showcase: str) -> None:
    """``en/``: every page of the Spanish site, translated; other files copied as they are."""
    target = site / ENGLISH
    for path in sorted(p for p in site.rglob("*") if p.is_file()):
        relative = path.relative_to(site)
        if relative.parts[0] == ENGLISH or relative.name in {MARKER, ".nojekyll"}:
            continue
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if relative == Path("presentacion.html"):
            destination.write_text(showcase, encoding="utf-8")
        elif path.suffix == ".html":
            english = translator.document(path.read_text(encoding="utf-8"))
            destination.write_text(
                english.replace(SWITCH_TO_ENGLISH, SWITCH_TO_SPANISH), encoding="utf-8"
            )
        else:
            shutil.copyfile(path, destination)


def link_languages(site: Path) -> None:
    """Each page's language link points to the same page in the other language."""
    for path in site.rglob("*.html"):
        relative = path.relative_to(site)
        if relative.parts[0] == ENGLISH:
            other = site.joinpath(*relative.parts[1:])
        else:
            other = site / ENGLISH / relative
        link = Path(os.path.relpath(other, path.parent)).as_posix()
        html = path.read_text(encoding="utf-8")
        if LANGUAGE_LINK in html:
            path.write_text(
                html.replace(f'href="{LANGUAGE_LINK}"', f'href="{link}"'), encoding="utf-8"
            )


@dataclass(frozen=True)
class BuiltSite:
    index: Path
    untranslated: list[str]  # texts of the English version left in Spanish


def build_site(
    target: Path,
    *,
    settings: Settings,
    snapshot: Path | None,
    dates: Sequence[date],
) -> BuiltSite:
    """Build the whole website (Spanish and English) in a temporary folder, then replace
    ``target`` with it."""
    if target.exists() and any(target.iterdir()) and not (target / MARKER).is_file():
        raise WebError(
            f"La carpeta {target} no está vacía y no es una web generada por este comando: "
            "elige otra con --salida."
        )
    with tempfile.TemporaryDirectory(prefix="web-") as temporary:
        work = Path(temporary)
        site = work / "sitio"
        site.mkdir()
        study, data = build_real(work, site, settings, snapshot=snapshot, dates=dates)
        sample = build_sample(work, site, settings)
        write_pages(site, sample=sample, study=study, data=data)
        write_logo(site)
        pages = {
            "es": showcase_page(settings.project_root / SHOWCASES["es"][0], *SHOWCASES["es"][1:])
        }
        try:
            pages["en"] = showcase_page(
                settings.project_root / SHOWCASES["en"][0], *SHOWCASES["en"][1:]
            )
        except WebError as error:  # the English site then shows the Spanish presentation
            console.print(f"[yellow]Presentación en inglés no disponible:[/yellow] {error}")
        (site / "presentacion.html").write_text(pages["es"], encoding="utf-8")
        translator = Translator(
            load_catalog(),
            keep={c.name for c in (*sample.companies, *study.run.companies)},
        )
        write_english(site, translator, pages.get("en", pages["es"]))
        link_languages(site)
        (site / ".nojekyll").write_text("", encoding="utf-8")  # plain files, no Jekyll
        (site / MARKER).write_text(f"{local_now():%Y-%m-%d %H:%M}\n", encoding="utf-8")
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(site, target)
    return BuiltSite(target / "index.html", sorted(translator.missing))


@app.callback()
def main() -> None:
    """Web pública: ejemplo completo y empresas reales con datos de uso libre (GitHub Pages)."""


@app.command("construir")
def build_command(
    salida: Annotated[
        Path | None, typer.Option(help="Carpeta donde se escribe la web (por defecto, _site).")
    ] = None,
    descarga: Annotated[
        Path | None,
        typer.Option(help="Usa una descarga sin cotizaciones ya hecha, en lugar de descargar."),
    ] = None,
    fecha: Annotated[
        list[str] | None,
        typer.Option(
            help="Fecha de análisis de las empresas reales, AAAA-MM-DD (se puede repetir). Por "
            "defecto, el cierre del semestre anterior y hoy."
        ),
    ] = None,
    abrir: Annotated[bool, typer.Option("--abrir", help="Abre la web al terminar.")] = False,
    pendientes: Annotated[
        Path | None,
        typer.Option(
            help="Fichero donde listar los textos que la versión inglesa deja en español."
        ),
    ] = None,
) -> None:
    """Construye la web pública: empresas reales sin cotizaciones, ejemplo completo y guías."""
    settings = Settings()
    today = local_today()
    dates = (
        sorted({parse_date(text) for text in fecha}) if fecha else [comparison_date(today), today]
    )
    target = salida or settings.project_root / "_site"
    try:
        built = build_site(target, settings=settings, snapshot=descarga, dates=dates)
    except (WebError, UniverseError, SnapshotError, ConfigError, CatalogError) as error:
        fail(str(error))
    except ValidationError as error:
        fail(f"Los datos descargados no son válidos:\n{error}")
    console.print(f"[bold]Web construida:[/bold] {built.index}")
    if built.untranslated:
        console.print(
            f"[yellow]{len(built.untranslated)} textos en inglés siguen en español[/yellow]"
            " (añádelos a src/company_analysis/i18n/en.yaml)."
        )
    if pendientes:
        pendientes.write_text(untranslated_report(built.untranslated), encoding="utf-8")
    if abrir:
        webbrowser.open(built.index.resolve().as_uri())


if __name__ == "__main__":
    app()
