"""Simple, explainable alert rules: rating downgrades, high leverage and large score changes."""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import StrEnum

from company_analysis.config import AlertsConfig, ScoreType
from company_analysis.formatting import format_date, format_money, format_number
from company_analysis.metrics import MetricTable, get_metric
from company_analysis.models import FinancialItem, RatingAction
from company_analysis.models.ratings import is_investment_grade, rating_notch
from company_analysis.normalization import CompanySnapshot, current_rating
from company_analysis.scoring import Score

Detail = str | float | None


class AlertRule(StrEnum):
    RATING_DOWNGRADE = "rating_downgrade"
    LEVERAGE = "leverage"
    SCORE_CHANGE = "score_change"

    @property
    def label(self) -> str:
        return _RULE_LABELS[self]


_RULE_LABELS = {
    AlertRule.RATING_DOWNGRADE: "Rebaja de rating",
    AlertRule.LEVERAGE: "Apalancamiento elevado",
    AlertRule.SCORE_CHANGE: "Cambio de puntuación",
}


@dataclass(frozen=True)
class Alert:
    rule: AlertRule
    issuer_id: str
    entity_id: str | None  # bond ISIN, or score type for score changes
    message: str
    details: Mapping[str, Detail] = field(default_factory=dict)


@dataclass(frozen=True)
class PreviousScores:
    """Scores of the previous run (the latest one with an earlier analysis date)."""

    run_id: str
    as_of: date
    config_hash: str
    scores: Mapping[tuple[str, ScoreType], Score]


def rating_downgrades(
    snapshots: Sequence[CompanySnapshot],
    ratings: Sequence[RatingAction],
    as_of: date,
    lookback_days: int,
) -> list[Alert]:
    """Bonds whose rating in force is worse than ``lookback_days`` before ``as_of``."""
    start = as_of - timedelta(days=lookback_days)
    by_isin: dict[str, list[RatingAction]] = defaultdict(list)
    for action in ratings:
        by_isin[action.isin].append(action)
    alerts = []
    for snapshot in snapshots:
        for bond in snapshot.bonds:
            isin = bond.bond.isin
            before, now = current_rating(by_isin[isin], start), current_rating(by_isin[isin], as_of)
            if (
                before is None
                or now is None
                or rating_notch(now.rating) <= rating_notch(before.rating)
            ):
                continue
            message = (
                f"Rebaja de rating del bono {isin}: de {before.rating} a {now.rating} "
                f"({now.agency}, {format_date(now.rating_date)})"
            )
            if is_investment_grade(before.rating) and not is_investment_grade(now.rating):
                message += "; pasa de grado de inversión a high yield"
            details: dict[str, Detail] = {
                "rating_anterior": before.rating,
                "rating_actual": now.rating,
                "agencia": now.agency,
                "fecha_rating": now.rating_date.isoformat(),
            }
            alerts.append(
                Alert(AlertRule.RATING_DOWNGRADE, snapshot.issuer_id, isin, message, details)
            )
    return alerts


def high_leverage(
    snapshots: Sequence[CompanySnapshot], metrics: MetricTable, threshold: float
) -> list[Alert]:
    """Net debt / EBITDA above the threshold, or positive net debt with EBITDA of zero or less."""
    alerts = []
    for snapshot in snapshots:
        result = metrics.result(snapshot.issuer_id, "net_debt_to_ebitda")
        limit = f"{format_number(threshold)}x"
        if result.value is not None:
            if result.value > threshold:
                message = (
                    f"Deuda neta/EBITDA de {format_number(result.value)}x, por encima del umbral "
                    f"de {limit}"
                )
                details: dict[str, Detail] = {"valor": result.value, "umbral": threshold}
                alerts.append(Alert(AlertRule.LEVERAGE, snapshot.issuer_id, None, message, details))
            continue
        debt = snapshot.stock(FinancialItem.TOTAL_DEBT)
        cash = snapshot.stock(FinancialItem.CASH)
        ebitda = snapshot.flow(FinancialItem.EBITDA)
        if not (debt.ok and cash.ok and ebitda.ok):
            continue
        net_debt = debt.number() - cash.number()
        if net_debt > 0 and ebitda.number() <= 0:
            currency = snapshot.currency
            kind = "negativo" if ebitda.number() < 0 else "nulo"
            message = (
                f"EBITDA {kind} ({format_money(ebitda.number(), currency)}) con deuda neta "
                f"positiva ({format_money(net_debt, currency)}): apalancamiento por encima de "
                f"cualquier umbral"
            )
            details = {"ebitda": ebitda.number(), "deuda_neta": net_debt, "umbral": threshold}
            alerts.append(Alert(AlertRule.LEVERAGE, snapshot.issuer_id, None, message, details))
    return alerts


def _contribution(score: Score, metric_id: str) -> float:
    for component in score.components:
        if component.metric_id == metric_id:
            return component.contribution or 0.0
    return 0.0


def score_changes(
    scores: Sequence[Score],
    previous: PreviousScores,
    min_change: float,
    config_hash: str,
) -> list[Alert]:
    """Shown scores that moved at least ``min_change`` points since the previous run."""
    alerts = []
    for score in scores:
        before = previous.scores.get((score.issuer_id, score.score_type))
        if score.value is None or before is None or before.value is None:
            continue
        change = score.value - before.value
        if abs(change) < min_change:
            continue
        drivers = sorted(
            (
                (
                    _contribution(score, c.metric_id) - _contribution(before, c.metric_id),
                    c.metric_id,
                )
                for c in score.components
            ),
            key=lambda item: -abs(item[0]),
        )
        main = [
            f"{get_metric(metric_id).name} ({'+' if delta > 0 else ''}{format_number(delta, 1)} "
            "puntos)"
            for delta, metric_id in drivers[:2]
            if abs(delta) >= 0.05
        ]
        message = (
            f"Puntuación de {score.score_type.label.lower()}: de {format_number(before.value, 0)} "
            f"a {format_number(score.value, 0)} ({'+' if change > 0 else ''}"
            f"{format_number(change, 0)} puntos) desde la ejecución a {format_date(previous.as_of)}"
        )
        if main:
            message += f". Factores que más lo explican: {', '.join(main)}"
        if previous.config_hash != config_hash:
            message += ". Atención: la configuración ha cambiado entre ambas ejecuciones"
        details: dict[str, Detail] = {
            "anterior": before.value,
            "actual": score.value,
            "ejecucion_anterior": previous.run_id,
        }
        alerts.append(
            Alert(AlertRule.SCORE_CHANGE, score.issuer_id, score.score_type.value, message, details)
        )
    return alerts


def evaluate_alerts(
    *,
    snapshots: Sequence[CompanySnapshot],
    ratings: Sequence[RatingAction],
    metrics: MetricTable,
    scores: Sequence[Score],
    previous: PreviousScores | None,
    config: AlertsConfig,
    config_hash: str,
    as_of: date,
) -> list[Alert]:
    """Every enabled rule, in a fixed order: downgrades, leverage, score changes."""
    alerts = []
    if config.rating_downgrade.enabled:
        alerts += rating_downgrades(
            snapshots, ratings, as_of, config.rating_downgrade.lookback_days
        )
    if config.leverage.enabled:
        alerts += high_leverage(snapshots, metrics, config.leverage.max_net_debt_to_ebitda)
    if config.score_change.enabled and previous is not None:
        alerts += score_changes(
            scores, previous, config.score_change.min_change_points, config_hash
        )
    return alerts
