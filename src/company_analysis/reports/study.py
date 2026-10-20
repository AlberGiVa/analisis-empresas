"""Report of the real-data study: peer comparison, changes between two dates and data quality.

It reads the results stored by the runs, like every other report, and adds what a study with real
data needs to be trusted: where each figure comes from and what was checked or assumed.
"""

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from statistics import median

import duckdb
from markupsafe import Markup, escape

from company_analysis.formatting import format_date, format_number
from company_analysis.metrics import MetricTable, get_metric
from company_analysis.metrics.base import format_value
from company_analysis.providers.public.provider import PublicDataResult
from company_analysis.reports.render import _common_context, environment
from company_analysis.reports.views import CompanyView, RunView
from company_analysis.storage.runs import load_metric_table

COLUMNS: tuple[tuple[str, str], ...] = (  # (metric, short header; the full name goes in a tooltip)
    ("market_cap_eur", "Capitaliz."),
    ("ev_to_ebitda", "EV/EBITDA"),
    ("pe_ratio", "PER"),
    ("fcf_yield", "FCF yield"),
    ("roic", "ROIC"),
    ("ebitda_margin", "Margen EBITDA"),
    ("revenue_growth", "Crec. ventas"),
    ("net_debt_to_ebitda", "DN/EBITDA"),
    ("interest_coverage", "Cobertura"),
    ("debt_to_equity", "Deuda/capital"),
)
REFERENCE = re.compile(r"^(\S+) cerrado el (\d{2}/\d{2}/\d{4})")
CHART_X, CHART_Y = "ev_to_ebitda", "net_debt_to_ebitda"


@dataclass(frozen=True)
class Cell:
    text: str
    available: bool
    note: str | None  # why it is missing


@dataclass(frozen=True)
class Column:
    header: str
    name: str  # full metric name


@dataclass(frozen=True)
class PeerRow:
    company: CompanyView
    period: str  # short form of the reference period, e.g. "Q1 03/04/2026"
    cells: tuple[Cell, ...]
    market_cap: float
    warnings: int  # data-quality warnings of the company (see the quality section)


@dataclass(frozen=True)
class Change:
    company: CompanyView
    reference_before: str | None
    reference_now: str
    equity: tuple[str, str, str]  # before, now, difference
    credit: tuple[str, str, str]


@dataclass(frozen=True)
class StudyView:
    run: RunView
    previous: RunView | None
    title: str
    description: str
    columns: tuple[Column, ...]
    groups: tuple[tuple[str, tuple[PeerRow, ...]], ...]  # (industry, rows)
    medians: tuple[str, ...]
    changes: tuple[Change, ...]
    chart: Markup
    chart_left_out: tuple[str, ...]  # companies not drawn, and why
    data: PublicDataResult | None


def _cell(metrics: MetricTable, issuer_id: str, metric_id: str) -> Cell:
    result = metrics.result(issuer_id, metric_id)
    if result.value is None:
        return Cell(result.status.label, False, result.detail)
    return Cell(format_value(result.value, get_metric(metric_id).unit), True, None)


def _medians(metrics: MetricTable, issuer_ids: Sequence[str]) -> tuple[str, ...]:
    texts = []
    for metric_id, _ in COLUMNS:
        values = [
            value
            for issuer_id in issuer_ids
            if (value := metrics.result(issuer_id, metric_id).value) is not None
        ]
        unit = get_metric(metric_id).unit
        texts.append(format_value(median(values), unit) if values else "—")
    return tuple(texts)


def _short_reference(text: str) -> str:
    match = REFERENCE.match(text)
    return f"{match.group(1)} {match.group(2)}" if match else text


def _score_text(value: float | None) -> str:
    return format_number(value, 0) if value is not None else "—"


def _difference(before: float | None, now: float | None) -> str:
    if before is None or now is None:
        return ""
    change = round(now) - round(before)
    return "=" if change == 0 else f"{change:+d}".replace("-", "−")


def _changes(run: RunView, previous: RunView | None) -> tuple[Change, ...]:
    if previous is None:
        return ()
    result = []
    for company in run.companies:
        before = next((c for c in previous.companies if c.issuer_id == company.issuer_id), None)
        result.append(
            Change(
                company=company,
                reference_before=before.reference_text if before else None,
                reference_now=company.reference_text,
                equity=(
                    _score_text(before.equity.value if before else None),
                    _score_text(company.equity.value),
                    _difference(before.equity.value if before else None, company.equity.value),
                ),
                credit=(
                    _score_text(before.credit.value if before else None),
                    _score_text(company.credit.value),
                    _difference(before.credit.value if before else None, company.credit.value),
                ),
            )
        )
    return tuple(result)


def _ticks(low: float, high: float, count: int = 5) -> list[float]:
    """Round tick values covering [low, high]."""
    raw = ((high - low) or 1.0) / count
    base = 10 ** math.floor(math.log10(raw))
    step = next(m * base for m in (1, 2, 2.5, 5, 10) if m * base >= raw)
    ticks, value = [], math.floor(low / step) * step
    while value <= high + step / 2:
        ticks.append(round(value, 6))
        value += step
    return ticks


def _overlaps(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def chart_svg(
    points: Sequence[tuple[str, str, float, float]], x_label: str, y_label: str
) -> Markup:
    """Scatter of two metrics, one labelled dot per company, with the group medians.

    ``points`` are (identifier, name, x, y). Colours are those of the showcase palette (validated
    for colour-blind readers); every value is also in the comparison table.
    """
    if len(points) < 2:
        return Markup('<p class="muted">No hay suficientes empresas con los dos datos.</p>')
    width, height, left, right, top, bottom = 720, 380, 56, 24, 16, 44
    xs, ys = [p[2] for p in points], [p[3] for p in points]
    x_ticks = _ticks(min(0.0, *xs), max(xs) * 1.08)
    y_ticks = _ticks(min(0.0, *ys), max(ys) * 1.1)
    x0, x1, y0, y1 = x_ticks[0], x_ticks[-1], y_ticks[0], y_ticks[-1]

    def sx(value: float) -> float:
        return left + (value - x0) / (x1 - x0) * (width - left - right)

    def sy(value: float) -> float:
        return top + (y1 - value) / (y1 - y0) * (height - top - bottom)

    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" class="chart" '
        f'aria-label="{escape(x_label)} frente a {escape(y_label)}">'
    ]
    parts.extend(
        f'<line x1="{sx(tick):.1f}" x2="{sx(tick):.1f}" y1="{top}" y2="{height - bottom}" '
        f'class="grid"/><text x="{sx(tick):.1f}" y="{height - bottom + 16}" '
        f'text-anchor="middle" class="tick">{format_number(tick, 1)}x</text>'
        for tick in x_ticks
    )
    parts.extend(
        f'<line x1="{left}" x2="{width - right}" y1="{sy(tick):.1f}" y2="{sy(tick):.1f}" '
        f'class="grid"/><text x="{left - 8}" y="{sy(tick) + 4:.1f}" text-anchor="end" '
        f'class="tick">{format_number(tick, 1)}x</text>'
        for tick in y_ticks
    )
    mx, my = median(xs), median(ys)
    parts.append(
        f'<line x1="{sx(mx):.1f}" x2="{sx(mx):.1f}" y1="{top}" y2="{height - bottom}" '
        f'class="median"/><line x1="{left}" x2="{width - right}" y1="{sy(my):.1f}" '
        f'y2="{sy(my):.1f}" class="median"/>'
        f'<text x="{sx(mx) + 4:.1f}" y="{top + 12}" class="tick">mediana</text>'
    )
    parts.append(
        f'<text x="{width - right}" y="{height - 6}" text-anchor="end" class="axis">'
        f"{escape(x_label)} →</text>"
        f'<text x="14" y="{top}" transform="rotate(-90 14 {top})" text-anchor="end" '
        f'class="axis">{escape(y_label)} →</text>'
    )
    placed: list[tuple[float, float, float, float]] = []  # label boxes already drawn
    for identifier, name, x, y in sorted(points, key=lambda p: p[3]):
        px, py = sx(x), sy(y)
        label_width = 7.5 * len(identifier) + 2
        # Right, left, above, below: the first spot that does not cover another label.
        for dx, dy, anchor in (
            (9, 4, "start"),
            (-9, 4, "end"),
            (0, -9, "middle"),
            (0, 17, "middle"),
        ):
            left_edge = px + dx - (label_width if anchor == "end" else 0)
            left_edge -= label_width / 2 if anchor == "middle" else 0
            box = (left_edge, py + dy - 11, left_edge + label_width, py + dy + 2)
            if not any(_overlaps(box, other) for other in placed):
                break
        placed.append(box)
        parts.append(
            f"<g><title>{escape(name)}: {format_number(x, 1)}x · {format_number(y, 1)}x</title>"
            f'<circle cx="{px:.1f}" cy="{py:.1f}" r="5" class="dot"/>'
            f'<text x="{px + dx:.1f}" y="{py + dy:.1f}" class="label" '
            f'text-anchor="{anchor}">{escape(identifier)}</text></g>'
        )
    parts.append("</svg>")
    return Markup("".join(parts))


def build_study_view(
    conn: duckdb.DuckDBPyConnection,
    run: RunView,
    previous: RunView | None,
    data: PublicDataResult | None,
    *,
    title: str,
    description: str,
) -> StudyView:
    metrics = load_metric_table(conn, run.record.run_id)
    warnings = {q.issuer_id: len(q.warnings) for q in data.companies} if data else {}
    rows = [
        PeerRow(
            company=company,
            period=_short_reference(company.reference_text),
            cells=tuple(_cell(metrics, company.issuer_id, metric) for metric, _ in COLUMNS),
            market_cap=metrics.result(company.issuer_id, "market_cap_eur").value or 0.0,
            warnings=warnings.get(company.issuer_id, 0),
        )
        for company in run.companies
    ]
    industries = sorted({row.company.industry_label for row in rows})
    groups = tuple(
        (
            industry,
            tuple(
                sorted(
                    (row for row in rows if row.company.industry_label == industry),
                    key=lambda row: -row.market_cap,
                )
            ),
        )
        for industry in industries
    )
    distorted = {q.issuer_id for q in data.companies if q.distorted_ebitda} if data else set()
    points, left_out = [], []
    for company in run.companies:
        x = metrics.result(company.issuer_id, CHART_X).value
        y = metrics.result(company.issuer_id, CHART_Y).value
        if x is None or y is None or x <= 0:
            left_out.append(f"{company.issuer_id} (sin uno de los dos datos o con EBITDA negativo)")
        elif company.issuer_id in distorted:
            left_out.append(
                f"{company.issuer_id} (EBITDA distorsionado por una partida no recurrente)"
            )
        else:
            points.append((company.issuer_id, company.name, x, y))
    return StudyView(
        run=run,
        previous=previous,
        title=title,
        description=description,
        columns=tuple(Column(header, get_metric(metric).name) for metric, header in COLUMNS),
        groups=groups,
        medians=_medians(metrics, [c.issuer_id for c in run.companies]),
        changes=_changes(run, previous),
        chart=chart_svg(points, "EV/EBITDA", "Deuda neta/EBITDA"),
        chart_left_out=tuple(left_out),
        data=data,
    )


def _date_text(value: date | None) -> str:
    return format_date(value) if value else "—"


def write_study_report(view: StudyView, directory: Path) -> Path:
    """Write ``estudio.html`` next to the run's ranking and fichas (links are relative)."""
    env = environment()
    env.filters["fecha"] = _date_text
    env.filters["num"] = format_number
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "estudio.html"
    context = _common_context(view.run)
    previous_date = format_date(view.previous.record.as_of_date) if view.previous else None
    path.write_text(
        env.get_template("estudio.html.j2").render(
            **context, study=view, previous_date=previous_date
        ),
        encoding="utf-8",
    )
    return path
