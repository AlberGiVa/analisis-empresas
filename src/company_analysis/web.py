"""Public website: the tool's results, open to anyone with the link (GitHub Pages).

A static site with these sections, plus how to read the results and what is new:
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

import shutil
import tempfile
import webbrowser
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from importlib.resources import files
from pathlib import Path
from typing import Annotated, Any

import duckdb
import typer
import yaml
from pydantic import ValidationError
from rich.console import Console

from company_analysis.cli import fail, parse_date
from company_analysis.clock import local_now, local_today
from company_analysis.config import ScoreModelConfig
from company_analysis.config_loader import ConfigError, LoadedConfig, load_config
from company_analysis.formatting import format_date
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
from company_analysis.reports.render import environment
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
    ("ejemplo", "Ejemplo completo", "ejemplo/ranking.html"),
    ("como-funciona", "Cómo funciona", "como-funciona.html"),
    ("novedades", "Novedades", "novedades.html"),
    ("presentacion", "Presentación", "presentacion.html"),
)
REAL_NOTICE = (
    "Empresas reales con datos públicos de uso libre: cuentas de la SEC y tipos de cambio del BCE. "
    "Sin cotizaciones, así que no hay capitalización, PER ni EV/EBITDA."
)
SAMPLE_NOTICE = (
    "Datos de ejemplo: empresas ficticias con datos inventados, para ver todo lo que hace la "
    "herramienta (cotizaciones, bonos, ratings y diferenciales incluidos)."
)
MARKER = ".web-generada"  # marks a folder this command may replace
WEB_METHODOLOGY = "metodologia-web.yaml"
NEWS = Path("docs") / "novedades.yaml"
# The showcase page (one self-contained file) is published as is, with a way back to the website.
SHOWCASE = Path("docs") / "muestra-luceiro-capital.html"
SHOWCASE_ANCHOR = '<p class="side-kicker">Análisis de empresas · muestra</p>'
LOGO = "luceiro-logo.webp"


class WebError(Exception):
    """The website cannot be built (the message says why, in Spanish)."""


def nav(active: str, notice: str | None = None) -> SiteNav:
    return SiteNav(links=SECTIONS, active=active, notice=notice)


# --- News ----------------------------------------------------------------------------------------
@dataclass(frozen=True)
class NewsEntry:
    day: date
    title: str
    text: str
    link: str | None  # page from the website root

    @property
    def day_text(self) -> str:
        return format_date(self.day)


def load_news(path: Path) -> list[NewsEntry]:
    """Entries of ``docs/novedades.yaml``, newest first."""
    if not path.is_file():
        raise WebError(f"Falta el fichero de novedades {path}.")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise WebError(f"{path.name}: debe ser una lista de novedades.")
    pages = {page for _, _, page in SECTIONS}
    entries = []
    for number, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise WebError(f"{path.name}, novedad {number}: debe tener fecha, titulo y texto.")
        day, title, text, link = (item.get(k) for k in ("fecha", "titulo", "texto", "enlace"))
        if isinstance(day, str):
            try:
                day = date.fromisoformat(day)
            except ValueError:
                day = None
        if not isinstance(day, date) or not isinstance(title, str) or not isinstance(text, str):
            raise WebError(
                f"{path.name}, novedad {number}: hacen falta fecha (AAAA-MM-DD), titulo y texto."
            )
        if link is not None and link not in pages:
            raise WebError(
                f"{path.name}, novedad {number}: el enlace {link!r} no es una página de la web "
                f"({', '.join(sorted(pages))})."
            )
        entries.append(NewsEntry(day, title.strip(), " ".join(text.split()), link))
    return sorted(entries, key=lambda entry: entry.day, reverse=True)


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
    """Fictitious companies with every feature, analysed at the demo dates."""
    config = load_config(settings.config_path)
    provider = SampleProvider(settings.sample_data_dir)
    with open_database(work / "ejemplo.duckdb") as conn:
        save_bundle(conn, provider.fetch(), provider.name)
        _analyse(conn, DEMO_AS_OF_DATES, config)
        view, _ = _latest_views(conn)
    write_reports(view, site, folder="ejemplo", site=nav("ejemplo", SAMPLE_NOTICE))
    return view


def _public_description(description: str) -> str:
    """The universe's first sentence, with the sources the website actually uses."""
    first = description.split(". ", maxsplit=1)[0].rstrip(".")
    return (
        f"{first}. Cuentas de la SEC (normas contables de EE. UU., sin ajustes) y tipos de cambio "
        "del BCE, sin cotizaciones."
    )


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
    news: Sequence[NewsEntry],
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
                "news": list(news)[:3],
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
        "novedades.html": ("web_novedades.html.j2", "novedades", {"news": news}),
    }
    for filename, (template, key, context) in pages.items():
        (site / filename).write_text(
            env.get_template(template).render(**common, site=nav(key), **context),
            encoding="utf-8",
        )


def write_brand(site: Path, showcase: Path) -> None:
    """The logo every page shows, and the showcase page as ``presentacion.html``."""
    logo = site / "marca" / LOGO
    logo.parent.mkdir()
    logo.write_bytes((files("company_analysis.reports") / "static" / LOGO).read_bytes())
    if not showcase.is_file():
        raise WebError(f"Falta la página de presentación {showcase}.")
    html = showcase.read_text(encoding="utf-8")
    if SHOWCASE_ANCHOR not in html or '<meta charset="utf-8">' not in html:
        raise WebError(
            f"{showcase.name} ha cambiado: no se encuentra dónde poner la vuelta a la web."
        )
    html = html.replace(
        '<meta charset="utf-8">',
        '<meta charset="utf-8"><meta name="robots" content="noindex, nofollow">',
        1,
    ).replace(
        SHOWCASE_ANCHOR,
        SHOWCASE_ANCHOR + '\n    <a href="index.html" style="font-weight:600;text-decoration:none;'
        'margin-top:-10px">← Volver a la web</a>',
        1,
    )
    (site / "presentacion.html").write_text(html, encoding="utf-8")


def build_site(
    target: Path,
    *,
    settings: Settings,
    snapshot: Path | None,
    dates: Sequence[date],
) -> Path:
    """Build the whole website in a temporary folder, then replace ``target`` with it."""
    if target.exists() and any(target.iterdir()) and not (target / MARKER).is_file():
        raise WebError(
            f"La carpeta {target} no está vacía y no es una web generada por este comando: "
            "elige otra con --salida."
        )
    news = load_news(settings.project_root / NEWS)
    with tempfile.TemporaryDirectory(prefix="web-") as temporary:
        work = Path(temporary)
        site = work / "sitio"
        site.mkdir()
        study, data = build_real(work, site, settings, snapshot=snapshot, dates=dates)
        sample = build_sample(work, site, settings)
        write_pages(site, sample=sample, study=study, data=data, news=news)
        write_brand(site, settings.project_root / SHOWCASE)
        (site / ".nojekyll").write_text("", encoding="utf-8")  # plain files, no Jekyll
        (site / MARKER).write_text(f"{local_now():%Y-%m-%d %H:%M}\n", encoding="utf-8")
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(site, target)
    return target / "index.html"


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
) -> None:
    """Construye la web pública: empresas reales sin cotizaciones, ejemplo completo y guías."""
    settings = Settings()
    today = local_today()
    dates = (
        sorted({parse_date(text) for text in fecha}) if fecha else [comparison_date(today), today]
    )
    target = salida or settings.project_root / "_site"
    try:
        index = build_site(target, settings=settings, snapshot=descarga, dates=dates)
    except (WebError, UniverseError, SnapshotError, ConfigError) as error:
        fail(str(error))
    except ValidationError as error:
        fail(f"Los datos descargados no son válidos:\n{error}")
    console.print(f"[bold]Web construida:[/bold] {index}")
    if abrir:
        webbrowser.open(index.resolve().as_uri())


if __name__ == "__main__":
    app()
