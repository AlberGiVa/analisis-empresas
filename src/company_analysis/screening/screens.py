"""Configurable screens: each company passes, fails or is indeterminate (missing data)."""

import operator
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from company_analysis.config import ConditionConfig, ScreenConfig
from company_analysis.metrics import MetricTable, get_metric
from company_analysis.metrics.base import format_value
from company_analysis.normalization import CompanySnapshot

_OPERATORS: dict[str, Callable[[float, float], bool]] = {
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
}
_OPERATOR_TEXT = {"<": "<", "<=": "≤", ">": ">", ">=": "≥"}


class ScreenOutcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    INDETERMINATE = "indeterminate"

    @property
    def label(self) -> str:
        return {"pass": "Cumple", "fail": "No cumple", "indeterminate": "Indeterminado"}[self]


@dataclass(frozen=True)
class ConditionResult:
    description: str  # e.g. "Deuda neta/EBITDA ≤ 2,5x"
    outcome: ScreenOutcome
    detail: str  # the company's value, or why it is unknown


@dataclass(frozen=True)
class ScreenResult:
    issuer_id: str
    screen_id: str
    outcome: ScreenOutcome
    conditions: tuple[ConditionResult, ...]


def _metric_condition(
    issuer_id: str, condition: ConditionConfig, metrics: MetricTable
) -> ConditionResult:
    definition = get_metric(condition.metric)
    threshold = format_value(condition.value, definition.unit)
    description = f"{definition.name} {_OPERATOR_TEXT[condition.operator]} {threshold}"
    result = metrics.result(issuer_id, condition.metric)
    if result.value is None:
        detail = f"{result.status.label}: {result.detail}" if result.detail else result.status.label
        return ConditionResult(description, ScreenOutcome.INDETERMINATE, detail)
    passed = _OPERATORS[condition.operator](result.value, condition.value)
    outcome = ScreenOutcome.PASS if passed else ScreenOutcome.FAIL
    return ConditionResult(
        description, outcome, f"valor: {format_value(result.value, definition.unit)}"
    )


def _membership(
    description: str, value: str, allowed: Sequence[str], labels: Sequence[str]
) -> ConditionResult:
    outcome = ScreenOutcome.PASS if value in allowed else ScreenOutcome.FAIL
    return ConditionResult(f"{description}: {', '.join(labels)}", outcome, f"valor: {value}")


def evaluate_screen(
    snapshot: CompanySnapshot, screen: ScreenConfig, metrics: MetricTable
) -> ScreenResult:
    issuer = snapshot.issuer
    conditions = []
    if screen.sectors:
        conditions.append(
            _membership(
                "Sector",
                issuer.sector.label,
                [sector.label for sector in screen.sectors],
                [sector.label for sector in screen.sectors],
            )
        )
    if screen.countries:
        conditions.append(_membership("País", issuer.country, screen.countries, screen.countries))
    conditions.extend(
        _metric_condition(snapshot.issuer_id, condition, metrics) for condition in screen.conditions
    )
    outcomes = {condition.outcome for condition in conditions}
    if ScreenOutcome.FAIL in outcomes:
        outcome = ScreenOutcome.FAIL
    elif ScreenOutcome.INDETERMINATE in outcomes:
        outcome = ScreenOutcome.INDETERMINATE
    else:
        outcome = ScreenOutcome.PASS
    return ScreenResult(snapshot.issuer_id, screen.id, outcome, tuple(conditions))


def evaluate_screens(
    snapshots: Sequence[CompanySnapshot], metrics: MetricTable, screens: Sequence[ScreenConfig]
) -> list[ScreenResult]:
    """Result of every screen for every company."""
    return [
        evaluate_screen(snapshot, screen, metrics) for screen in screens for snapshot in snapshots
    ]
