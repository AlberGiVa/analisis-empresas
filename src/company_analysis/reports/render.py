"""Report files of a run: ranking (HTML and CSV for Excel) and one HTML ficha per company."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape

from company_analysis.clock import local_now
from company_analysis.config import ScoreType
from company_analysis.formatting import format_date
from company_analysis.reports.views import AlertLine, CompanyView, RunView, ScoreView
from company_analysis.screening import ScreenOutcome


@dataclass(frozen=True)
class ReportFiles:
    directory: Path
    ranking_html: Path
    ranking_csv: Path
    fichas: tuple[Path, ...]


def environment() -> Environment:
    """Jinja2 with autoescaping (notes typed by analysts are never interpreted as HTML)."""
    return Environment(
        loader=PackageLoader("company_analysis.reports", "templates"),
        autoescape=select_autoescape(enabled_extensions=("html", "j2")),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _common_context(view: RunView) -> dict[str, Any]:
    record = view.record
    return {
        "view": view,
        "record": record,
        "run_date": format_date(record.as_of_date),
        "cutoff": f"{record.data_cutoff:%d/%m/%Y %H:%M}",
        "generated": f"{local_now():%d/%m/%Y %H:%M}",
        "disclaimer": view.disclaimer,
    }


def _position(view: RunView, score_type: ScoreType) -> dict[str, int]:
    shown = [c for c in view.ranking(score_type) if _score(c, score_type).value is not None]
    return {company.issuer_id: index for index, company in enumerate(shown, start=1)}


def _score(company: CompanyView, score_type: ScoreType) -> ScoreView:
    return company.equity if score_type is ScoreType.EQUITY else company.credit


def ranking_frame(view: RunView) -> pd.DataFrame:
    """One row per company, in the order of the equity ranking (columns in Spanish)."""
    equity_position = _position(view, ScoreType.EQUITY)
    credit_position = _position(view, ScoreType.CREDIT)
    rows = []
    for company in view.ranking(ScoreType.EQUITY):
        row: dict[str, object] = {
            "Empresa": company.name,
            "Identificador": company.issuer_id,
            "Sector": company.sector_label,
            "País": company.country,
        }
        for score_type, positions in (
            (ScoreType.EQUITY, equity_position),
            (ScoreType.CREDIT, credit_position),
        ):
            score = _score(company, score_type)
            label = score_type.label.lower()
            row[f"Posición {label}"] = positions.get(company.issuer_id)
            row[f"Puntuación {label}"] = None if score.value is None else round(score.value, 1)
            row[f"Cobertura {label} (%)"] = round(score.coverage * 100, 1)
            row[f"Motivo sin puntuación {label}"] = score.reason or ""
        row["Alertas"] = len(company.alerts)
        row["Filtros que cumple"] = ", ".join(
            screen.name for screen in company.screens if screen.outcome is ScreenOutcome.PASS
        )
        rows.append(row)
    frame = pd.DataFrame(rows)
    for column in ("Posición renta variable", "Posición crédito"):
        frame[column] = frame[column].astype("Int64")
    return frame


def write_reports(view: RunView, output_dir: Path) -> ReportFiles:
    """Write ``<output_dir>/<run_id>/``: ranking.html, ranking.csv and fichas/<company>.html."""
    directory = output_dir / view.record.run_id
    fichas_dir = directory / "fichas"
    fichas_dir.mkdir(parents=True, exist_ok=True)
    env = environment()
    context = _common_context(view)
    alerts: list[tuple[CompanyView, AlertLine]] = [
        (company, alert) for company in view.companies for alert in company.alerts
    ]
    ranking_html = directory / "ranking.html"
    ranking_html.write_text(
        env.get_template("ranking.html.j2").render(
            **context,
            equity=view.ranking(ScoreType.EQUITY),
            credit=view.ranking(ScoreType.CREDIT),
            alerts=alerts,
            alerts_count=len(alerts),
            companies_count=len(view.companies),
        ),
        encoding="utf-8",
    )
    ranking_csv = directory / "ranking.csv"
    # Separator ";" and decimal comma, UTF-8 with BOM: opens directly in Excel in Spanish.
    ranking_frame(view).to_csv(ranking_csv, sep=";", decimal=",", index=False, encoding="utf-8-sig")
    template = env.get_template("ficha.html.j2")
    fichas = []
    for company in view.companies:
        path = directory / company.ficha_path
        path.write_text(template.render(**context, company=company), encoding="utf-8")
        fichas.append(path)
    return ReportFiles(directory, ranking_html, ranking_csv, tuple(fichas))
