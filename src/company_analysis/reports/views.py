"""Everything a report or the panel needs about one run, with Spanish texts and formatted values.

Results (metrics, scores, screens, alerts) are read as stored by the run. Descriptive context
(prices, bonds, financial history) is rebuilt from the input data with the run's own analysis
date, data cut-off and configuration: the data are append-only, so it is exactly what the run saw.
"""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

import duckdb

from company_analysis.config import AnalysisConfig, ScoreModelConfig, ScoreType
from company_analysis.config_loader import parse_config
from company_analysis.figures import Status
from company_analysis.formatting import format_date, format_number
from company_analysis.journal import JournalEntry, list_entries
from company_analysis.metrics import (
    MetricCategory,
    MetricResult,
    MetricTable,
    all_metrics,
    get_metric,
)
from company_analysis.metrics.base import format_value
from company_analysis.models import FinancialFact, FinancialItem, FiscalPeriod
from company_analysis.normalization import CompanySnapshot, build_snapshots, comparable_year
from company_analysis.scoring import Score
from company_analysis.screening import Alert, ConditionResult, ScreenOutcome, ScreenResult
from company_analysis.storage import read_bundle
from company_analysis.storage.runs import (
    RunRecord,
    RunStatus,
    get_run,
    load_alerts,
    load_metric_table,
    load_scores,
    load_screen_results,
)

DISCLAIMER = (
    "Las puntuaciones resumen métricas comparadas con empresas similares y las alertas señalan "
    "hechos concretos. Nada de lo que aparece aquí es una recomendación de compra o venta."
)
HISTORY = timedelta(days=3 * 366)
HISTORY_YEARS = 3
SPREAD_METRIC = "spread_vs_rating_bucket"


class ReportError(Exception):
    """The run does not exist or cannot be shown."""


def format_input(value: float) -> str:
    """Inputs mix amounts, rates and counts: more decimals for small numbers."""
    magnitude = abs(value)
    decimals = 4 if magnitude < 10 else 2 if magnitude < 1000 else 1
    return format_number(value, decimals)


@dataclass(frozen=True)
class MetricLine:
    metric_id: str
    name: str
    value: float | None
    value_text: str
    status_label: str | None  # None when the value is available
    detail: str | None
    formula: str
    inputs: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class FactorLine:
    metric: MetricLine
    reference_text: str | None
    percentile_text: str | None
    weight_text: str
    contribution_text: str | None


@dataclass(frozen=True)
class ScoreView:
    score_type: ScoreType
    title: str
    value: float | None
    value_text: str
    coverage: float
    coverage_text: str
    reason: str | None
    factors: tuple[FactorLine, ...]


@dataclass(frozen=True)
class BondLine:
    isin: str
    currency: str
    seniority: str
    coupon_text: str
    maturity_text: str
    rating_text: str
    yield_text: str
    spread_text: str
    comparison_text: str


@dataclass(frozen=True)
class HistoryView:
    currency: str
    years: tuple[str, ...]
    periods: tuple[str, ...]
    rows: tuple[tuple[str, tuple[str, ...]], ...]


@dataclass(frozen=True)
class AlertLine:
    rule_label: str
    message: str


@dataclass(frozen=True)
class ScreenLine:
    name: str
    outcome: ScreenOutcome
    outcome_label: str
    conditions: tuple[ConditionResult, ...]


@dataclass(frozen=True)
class NoteLine:
    date_text: str
    author: str
    decision_label: str
    text: str


@dataclass(frozen=True)
class CompanyView:
    issuer_id: str
    name: str
    lei: str | None
    country: str
    sector_label: str
    industry_label: str
    currency: str
    listing_text: str
    reference_text: str
    price_text: str
    equity: ScoreView
    credit: ScoreView
    magnitudes: tuple[MetricLine, ...]
    bonds: tuple[BondLine, ...]
    alerts: tuple[AlertLine, ...]
    screens: tuple[ScreenLine, ...]
    notes: tuple[NoteLine, ...]
    history: HistoryView

    @property
    def ficha_path(self) -> str:
        return f"fichas/{self.issuer_id}.html"


@dataclass(frozen=True)
class RunView:
    record: RunRecord
    config: AnalysisConfig
    companies: tuple[CompanyView, ...]  # alphabetical
    formulas: tuple[tuple[str, str], ...]  # (metric name, formula) of every metric
    disclaimer: str = DISCLAIMER

    def company(self, issuer_id: str) -> CompanyView:
        return next(c for c in self.companies if c.issuer_id == issuer_id)

    def ranking(self, score_type: ScoreType) -> list[CompanyView]:
        """Companies with a shown score first (highest first), then the others by name."""

        def key(company: CompanyView) -> tuple[bool, float, str]:
            value = _score(company, score_type).value
            return (value is None, -(value or 0.0), company.name)

        return sorted(self.companies, key=key)


def _score(company: CompanyView, score_type: ScoreType) -> ScoreView:
    return company.equity if score_type is ScoreType.EQUITY else company.credit


def _metric_line(metric_id: str, result: MetricResult) -> MetricLine:
    definition = get_metric(metric_id)
    ok = result.value is not None
    return MetricLine(
        metric_id=metric_id,
        name=definition.name,
        value=result.value,
        value_text=format_value(result.value, definition.unit) if result.value is not None else "—",
        status_label=None if ok else result.status.label,
        detail=result.detail,
        formula=definition.formula,
        inputs=tuple((label, format_input(value)) for label, value in result.inputs.items()),
    )


def _score_view(
    score: Score, model: ScoreModelConfig, metrics: MetricTable, score_type: ScoreType
) -> ScoreView:
    total_weight = sum(factor.weight for factor in model.factors)
    factors = []
    for component in score.components:
        line = _metric_line(
            component.metric_id, metrics.result(score.issuer_id, component.metric_id)
        )
        if component.status is Status.INSUFFICIENT_PEERS:
            line = MetricLine(
                line.metric_id,
                line.name,
                line.value,
                line.value_text,
                component.status.label,
                component.detail,
                line.formula,
                line.inputs,
            )
        reference = (
            f"{component.reference_group.label} ({component.peer_count} empresas)"
            if component.reference_group is not None
            else None
        )
        factors.append(
            FactorLine(
                metric=line,
                reference_text=reference,
                percentile_text=(
                    format_number(component.percentile, 0)
                    if component.percentile is not None
                    else None
                ),
                weight_text=f"{format_number(component.weight / total_weight * 100, 0)} %",
                contribution_text=(
                    format_number(component.contribution, 1)
                    if component.contribution is not None
                    else None
                ),
            )
        )
    return ScoreView(
        score_type=score_type,
        title=model.name,
        value=score.value,
        value_text=format_number(score.value, 0) if score.value is not None else "No disponible",
        coverage=score.coverage,
        coverage_text=f"{format_number(score.coverage * 100, 0)} %",
        reason=score.reason,
        factors=tuple(factors),
    )


def _bond_lines(snapshot: CompanySnapshot, metrics: MetricTable) -> tuple[BondLine, ...]:
    results = {row.entity_id: row.result for row in metrics.bond_rows(SPREAD_METRIC)}
    lines = []
    for bond in snapshot.bonds:
        instrument = bond.bond
        result = results.get(instrument.isin)
        if result is None:
            comparison = "—"
        elif result.value is not None:
            median = next(
                (v for k, v in result.inputs.items() if k.startswith("Mediana del tramo")), None
            )
            sign = "+" if result.value > 0 else ""
            comparison = f"{sign}{format_number(result.value, 0)} pb"
            if median is not None:
                comparison += f" (mediana del tramo: {format_number(median, 0)} pb)"
        else:
            comparison = f"{result.status.label}: {result.detail}"
        lines.append(
            BondLine(
                isin=instrument.isin,
                currency=instrument.currency,
                seniority=instrument.seniority.label,
                coupon_text=f"{format_number(instrument.coupon_pct, 3)} %",
                maturity_text=format_date(instrument.maturity_date),
                rating_text=(
                    f"{bond.rating.rating} ({bond.rating.agency})" if bond.rating else "Sin rating"
                ),
                yield_text=(f"{format_number(bond.quote.yield_pct, 2)} %" if bond.quote else "—"),
                spread_text=(
                    f"{format_number(bond.spread.number(), 0)} pb"
                    if bond.spread.ok
                    else bond.spread.status.label
                ),
                comparison_text=comparison,
            )
        )
    return tuple(lines)


_HISTORY_ROWS = (
    ("Ventas", (FinancialItem.REVENUE,), ()),
    ("EBITDA", (FinancialItem.EBITDA,), ()),
    ("Beneficio neto atribuible", (FinancialItem.NET_INCOME,), ()),
    (
        "Flujo de caja libre",
        (FinancialItem.OPERATING_CASH_FLOW,),
        (FinancialItem.CAPITAL_EXPENDITURE,),
    ),
    ("Deuda neta", (FinancialItem.TOTAL_DEBT,), (FinancialItem.CASH,)),
)


def _history(facts: Sequence[FinancialFact], currency: str) -> HistoryView:
    """Last fiscal years side by side, labelled with the calendar year they compare with."""
    annual: dict[tuple[date, FinancialItem], float] = {}
    for fact in facts:
        if fact.fiscal_period is FiscalPeriod.FY:
            annual[(fact.period_end, fact.item)] = fact.value
    ends = sorted({end for end, _ in annual})[-HISTORY_YEARS:]
    rows = []
    for label, added, subtracted in _HISTORY_ROWS:
        values = []
        for end in ends:
            parts = [annual.get((end, item)) for item in (*added, *subtracted)]
            if any(part is None for part in parts):
                values.append("—")
                continue
            total = sum(annual[(end, item)] for item in added) - sum(
                annual[(end, item)] for item in subtracted
            )
            values.append(format_number(total, 0))
        rows.append((label, tuple(values)))
    return HistoryView(
        currency=currency,
        years=tuple(str(comparable_year(end)) for end in ends),
        periods=tuple(f"FY {format_date(end)}" for end in ends),
        rows=tuple(rows),
    )


def _company_view(
    snapshot: CompanySnapshot,
    config: AnalysisConfig,
    metrics: MetricTable,
    scores: Mapping[tuple[str, ScoreType], Score],
    screens: Sequence[ScreenResult],
    alerts: Sequence[Alert],
    notes: Sequence[JournalEntry],
    facts: Sequence[FinancialFact],
) -> CompanyView:
    issuer = snapshot.issuer
    reference = snapshot.reference
    if reference is None:
        reference_text = "Sin estados financieros publicados"
    else:
        reference_text = f"{reference.label}, publicado el {format_date(reference.published_at)}"
    if snapshot.price.ok and snapshot.price_date is not None and snapshot.equity is not None:
        price_text = (
            f"{format_number(snapshot.price.number(), 2)} {snapshot.equity.currency} "
            f"del {format_date(snapshot.price_date)}"
        )
    else:
        price_text = f"{snapshot.price.status.label}: {snapshot.price.detail}"
    listing = (
        f"{snapshot.equity.exchange} · {snapshot.equity.currency} · {snapshot.equity.isin}"
        if snapshot.equity is not None
        else "Sin acción cotizada"
    )
    screen_names = {screen.id: screen.name for screen in config.screens}
    magnitude_ids = [m.metric_id for m in all_metrics() if m.category is MetricCategory.MAGNITUDE]
    return CompanyView(
        issuer_id=issuer.issuer_id,
        name=issuer.name,
        lei=issuer.lei,
        country=issuer.country,
        sector_label=issuer.sector.label,
        industry_label=issuer.industry.label,
        currency=issuer.reporting_currency,
        listing_text=listing,
        reference_text=reference_text,
        price_text=price_text,
        equity=_score_view(
            scores[(issuer.issuer_id, ScoreType.EQUITY)],
            config.scoring.equity,
            metrics,
            ScoreType.EQUITY,
        ),
        credit=_score_view(
            scores[(issuer.issuer_id, ScoreType.CREDIT)],
            config.scoring.credit,
            metrics,
            ScoreType.CREDIT,
        ),
        magnitudes=tuple(
            _metric_line(metric_id, metrics.result(issuer.issuer_id, metric_id))
            for metric_id in magnitude_ids
        ),
        bonds=_bond_lines(snapshot, metrics),
        alerts=tuple(AlertLine(alert.rule.label, alert.message) for alert in alerts),
        screens=tuple(
            ScreenLine(
                screen_names.get(result.screen_id, result.screen_id),
                result.outcome,
                result.outcome.label,
                result.conditions,
            )
            for result in screens
        ),
        notes=tuple(
            NoteLine(format_date(note.entry_date), note.author, note.decision.label, note.text)
            for note in notes
        ),
        history=_history(facts, issuer.reporting_currency),
    )


def build_run_view(conn: duckdb.DuckDBPyConnection, run_id: str) -> RunView:
    """Assemble the view of a completed run."""
    record = get_run(conn, run_id)
    if record is None:
        raise ReportError(f"No existe la ejecución {run_id}.")
    if record.status is not RunStatus.COMPLETED:
        raise ReportError(f"La ejecución {run_id} no se completó: {record.error}")
    config = parse_config(record.config_snapshot, source=f"configuración de {run_id}").config
    as_of = record.as_of_date
    bundle = read_bundle(
        conn, as_of=as_of, cutoff=record.data_cutoff, history_start=as_of - HISTORY
    )
    snapshots = build_snapshots(bundle, as_of, config.normalization)
    metrics = load_metric_table(conn, run_id)
    scores = {(s.issuer_id, s.score_type): s for s in load_scores(conn, run_id)}
    screens: dict[str, list[ScreenResult]] = defaultdict(list)
    for screen in load_screen_results(conn, run_id):
        screens[screen.issuer_id].append(screen)
    alerts: dict[str, list[Alert]] = defaultdict(list)
    for alert in load_alerts(conn, run_id):
        alerts[alert.issuer_id].append(alert)
    notes: dict[str, list[JournalEntry]] = defaultdict(list)
    for note in list_entries(conn):
        notes[note.issuer_id].append(note)
    facts: dict[str, list[FinancialFact]] = defaultdict(list)
    for fact in bundle.financial_facts:
        facts[fact.issuer_id].append(fact)
    companies = [
        _company_view(
            snapshot,
            config,
            metrics,
            scores,
            screens[snapshot.issuer_id],
            alerts[snapshot.issuer_id],
            notes[snapshot.issuer_id],
            facts[snapshot.issuer_id],
        )
        for snapshot in snapshots
    ]
    return RunView(
        record=record,
        config=config,
        companies=tuple(sorted(companies, key=lambda company: company.name)),
        formulas=tuple((m.name, m.formula) for m in all_metrics()),
    )
