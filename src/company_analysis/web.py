"""Public website: tables and views of the tool, open to anyone with the link (GitHub Pages).

- Panel: the day at a glance (companies, alerts, currencies).
- Empresas: real US companies with sources that may be republished (SEC accounts, no share prices,
  methodology ``estudio-real/metodologia-web.yaml``), with a sheet per company.
- Divisas: euro exchange rates of the ECB.
- Ejemplos: one fictitious company per case the tool handles.
- Academy: terms and metric formulas, for whoever wants them.

Every page wears the Luceiro Capital identity, in Spanish and English (``en/``). The analyst's
journal and the technical documentation of the tool are never published. Everything is computed in
a temporary folder; GitHub Actions builds and publishes it (``.github/workflows/web.yml``).
Decision 0018.

Run it with ``uv run python -m company_analysis.web construir`` (Spanish CLI).
"""

import csv
import io
import json
import os
import shutil
import tempfile
import webbrowser
from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from importlib.resources import files
from pathlib import Path
from typing import Annotated, Any

import duckdb
import typer
from markupsafe import Markup
from pydantic import ValidationError
from rich.console import Console

from company_analysis.cli import fail, parse_date
from company_analysis.clock import local_now, local_today
from company_analysis.config import ScoreModelConfig
from company_analysis.config_loader import ConfigError, LoadedConfig, load_config
from company_analysis.formatting import format_date, format_number
from company_analysis.i18n import CatalogError, Translator, load_catalog, untranslated_report
from company_analysis.metrics import MetricCategory, all_metrics, get_metric
from company_analysis.metrics.base import MetricDefinition
from company_analysis.models import FxRate
from company_analysis.pipeline import AnalysisError, run_analysis
from company_analysis.provenance import git_commit
from company_analysis.providers import SampleProvider
from company_analysis.providers.public.downloads import Request, download, plan
from company_analysis.providers.public.market import ecb_rates
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
    ("inicio", "Panel", "index.html"),
    ("indices", "Índices", "indices.html"),
    ("reales", "Empresas", "reales/index.html"),
    ("mercados", "Mercados", "mercados.html"),
    ("ejemplo", "Ejemplos", "ejemplo/index.html"),
    ("academy", "Academy", "academy.html"),
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
            plan(universe, local_today(), prices=False, currencies=FX_CURRENCIES)
            + market_requests(local_today()),
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


# --- Currencies ----------------------------------------------------------------------------------
FX_CURRENCIES = ("USD", "GBP", "CHF", "JPY", "CAD", "AUD", "SEK", "NOK", "DKK", "PLN")
CURRENCY_NAMES = {
    "USD": "Dólar estadounidense",
    "GBP": "Libra esterlina",
    "CHF": "Franco suizo",
    "JPY": "Yen japonés",
    "PLN": "Esloti polaco",
    "CAD": "Dólar canadiense",
    "AUD": "Dólar australiano",
    "SEK": "Corona sueca",
    "NOK": "Corona noruega",
    "DKK": "Corona danesa",
}
FX_BACK = (7, 30, 365)  # days back for the changes: a week, a month, a year (plus year to date)


@dataclass(frozen=True)
class FxRow:
    currency: str
    name: str
    day: date
    rate_text: str  # units of the currency per euro (ECB convention)
    inverse_text: str  # euros per unit
    changes: tuple[tuple[str, str], ...]  # (text, "up"/"down"/"") per period
    spark: Markup


def _rate_at(series: Sequence[FxRate], day: date) -> float | None:
    """Rate of the last business day on or before ``day``."""
    index = bisect_right([rate.rate_date for rate in series], day) - 1
    return series[index].units_per_eur if index >= 0 else None


def _change(now: float, before: float | None) -> tuple[str, str]:
    if before is None or before <= 0:
        return ("—", "")
    change = now / before - 1
    text = f"{format_number(change * 100, 2)} %"
    if change > 0:
        return (f"+{text}", "up")
    return (text.replace("-", "−"), "down" if change < 0 else "")


def sparkline(values: Sequence[float], width: int = 140, height: int = 36) -> Markup:
    """A one-year line, scaled to its own range (the table carries the figures)."""
    if len(values) < 2:
        return Markup("")
    low, high = min(values), max(values)
    span = (high - low) or 1.0
    step = width / (len(values) - 1)
    points = " ".join(
        f"{i * step:.1f},{height - 3 - (v - low) / span * (height - 6):.1f}"
        for i, v in enumerate(values)
    )
    return Markup(
        f'<svg class="spark" viewBox="0 0 {width} {height}" aria-hidden="true">'
        f'<polyline points="{points}"/></svg>'
    )


def fx_rows(snapshot: Path) -> list[FxRow]:
    """Latest ECB rate of every currency in the download, with its changes and a year of history."""
    rows = []
    for path in sorted((snapshot / "bce").glob("*.csv")):
        series = ecb_rates(path.read_text(encoding="utf-8"))
        if not series:
            continue
        last = series[-1]
        now = last.units_per_eur
        references = [_rate_at(series, last.rate_date - timedelta(days=d)) for d in FX_BACK]
        references.append(_rate_at(series, date(last.rate_date.year - 1, 12, 31)))
        year = [r.units_per_eur for r in series if r.rate_date > last.rate_date - timedelta(365)]
        rows.append(
            FxRow(
                currency=last.currency,
                name=CURRENCY_NAMES.get(last.currency, last.currency),
                day=last.rate_date,
                rate_text=format_number(now, 4),
                inverse_text=format_number(1 / now, 4),
                changes=tuple(_change(now, before) for before in references),
                spark=sparkline(year),
            )
        )
    order = {currency: index for index, currency in enumerate(FX_CURRENCIES)}
    return sorted(rows, key=lambda row: (order.get(row.currency, len(order)), row.currency))


# --- Markets: live on the page, with the figures of the build as a fallback ----------------------
CURVE_TENORS = ("3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "15Y", "20Y", "30Y")
ECB_DATA = "https://data-api.ecb.europa.eu/service/data"
DEPOSIT_RATE = "FM/D.U2.EUR.4F.KR.DFR.LEV"  # ECB deposit facility rate (daily)
BOND_COUNTRIES = ("ES", "DE", "IT", "FR")
BONDS_10Y = f"IRS/M.{'+'.join(BOND_COUNTRIES)}.L.L40.CI.0000.EUR.N.Z"  # 10-year yields (monthly)


def market_requests(today: date) -> list[Request]:
    """€STR and the euro AAA yield curve (ECB): optional, a failure never stops the website."""
    start = (today - timedelta(days=400)).isoformat()
    keys = "+".join(f"SR_{tenor}" for tenor in CURVE_TENORS)
    bonds_start = (today - timedelta(days=6 * 366)).isoformat()[:7]  # monthly series: YYYY-MM
    return [
        Request(
            "mercados/estr.csv",
            f"{ECB_DATA}/EST/B.EU000A2X2A25.WT?startPeriod={start}&format=csvdata",
            "Banco Central Europeo (€STR)",
            "browser",
            required=False,
        ),
        Request(
            "mercados/curva.csv",
            f"{ECB_DATA}/YC/B.U2.EUR.4F.G_N_A.SV_C_YM.{keys}?startPeriod={start}&format=csvdata",
            "Banco Central Europeo (curva AAA del euro)",
            "browser",
            required=False,
        ),
        Request(
            "mercados/dfr.csv",
            f"{ECB_DATA}/{DEPOSIT_RATE}?startPeriod={start}&format=csvdata",
            "Banco Central Europeo (tipo de la facilidad de depósito)",
            "browser",
            required=False,
        ),
        Request(
            "mercados/bonos10.csv",
            f"{ECB_DATA}/{BONDS_10Y}?startPeriod={bonds_start}&format=csvdata",
            "Banco Central Europeo (deuda pública a 10 años)",
            "browser",
            required=False,
        ),
    ]


def _ecb_csv(path: Path) -> list[tuple[str, str, float]]:
    """(series key, ISO date, value) of an ECB CSV file; empty if the file is missing."""
    if not path.is_file():
        return []
    rows = []
    for row in csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))):
        value = (row.get("OBS_VALUE") or "").strip()
        if value:
            rows.append((row["KEY"], row["TIME_PERIOD"], float(value)))
    return rows


def market_data(snapshot: Path) -> dict[str, Any]:
    """Series the market views draw before (or without) the live update."""
    fx: dict[str, list[tuple[str, float]]] = {}
    for path in sorted((snapshot / "bce").glob("*.csv")):
        for rate in ecb_rates(path.read_text(encoding="utf-8")):
            fx.setdefault(rate.currency, []).append(
                (rate.rate_date.isoformat(), rate.units_per_eur)
            )
    last = max((series[-1][0] for series in fx.values()), default=None)
    cut = (date.fromisoformat(last) - timedelta(days=731)).isoformat() if last else ""  # two years
    estr = [(day, value) for _, day, value in _ecb_csv(snapshot / "mercados" / "estr.csv")]
    curve: dict[str, dict[str, float]] = {}
    for key, day, value in _ecb_csv(snapshot / "mercados" / "curva.csv"):
        curve.setdefault(day, {})[key.rsplit("SR_", 1)[-1]] = value
    deposit = [(day, value) for _, day, value in _ecb_csv(snapshot / "mercados" / "dfr.csv")]
    bonds: dict[str, list[tuple[str, float]]] = {}
    for key, day, value in _ecb_csv(snapshot / "mercados" / "bonos10.csv"):
        bonds.setdefault(key.split(".")[2], []).append((day, value))  # IRS.M.ES.L.L40…
    return {
        "fx": {cur: [list(p) for p in series if p[0] >= cut] for cur, series in fx.items()},
        "estr": [list(p) for p in sorted(estr)],
        "curve": dict(sorted(curve.items())),
        "dfr": [list(p) for p in sorted(deposit)],
        "bonds": {country: [list(p) for p in sorted(s)] for country, s in bonds.items()},
        "currencies": list(FX_CURRENCIES),
        "tenors": list(CURVE_TENORS),
        "countries": list(BOND_COUNTRIES),
        "keys": {"dfr": DEPOSIT_RATE, "bonds": BONDS_10Y},
    }


def json_script(data: object) -> Markup:
    """JSON that is safe inside <script type="application/json">."""
    return Markup(json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"))


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
    fx = fx_rows(data.snapshot)
    market = json_script(market_data(data.snapshot))
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
                "fx": fx,
                "market": market,
                "score_bars": json_script(
                    [
                        {
                            "name": c.name,
                            "href": f"reales/{c.ficha_path}",
                            "a": None if c.equity.value is None else round(c.equity.value),
                            "c": None if c.credit.value is None else round(c.credit.value),
                        }
                        for c in study.run.companies
                    ]
                ),
            },
        ),
        "mercados.html": ("web_mercados.html.j2", "mercados", {"fx": fx, "market": market}),
        "indices.html": ("web_indices.html.j2", "indices", {}),
        "academy.html": (
            "web_academy.html.j2",
            "academy",
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
    """The logo and the charts script every page uses."""
    folder = site / "marca"
    folder.mkdir()
    for name in (LOGO, "graficos.js"):
        (folder / name).write_bytes(
            (files("company_analysis.reports") / "static" / name).read_bytes()
        )


def write_english(site: Path, translator: Translator) -> None:
    """``en/``: every page of the Spanish site, translated; other files copied as they are."""
    target = site / ENGLISH
    for path in sorted(p for p in site.rglob("*") if p.is_file()):
        relative = path.relative_to(site)
        if relative.parts[0] == ENGLISH or relative.name in {MARKER, ".nojekyll"}:
            continue
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".html":
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
        translator = Translator(
            load_catalog(),
            keep={c.name for c in (*sample.companies, *study.run.companies)},
        )
        write_english(site, translator)
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
