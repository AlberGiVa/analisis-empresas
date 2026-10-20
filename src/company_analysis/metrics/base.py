"""Building blocks of the metric registry: definitions, results and safe arithmetic."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from company_analysis.config import MetricsConfig
from company_analysis.figures import Figure, Status
from company_analysis.formatting import format_number
from company_analysis.models import Industry
from company_analysis.normalization import CompanySnapshot


class MetricCategory(StrEnum):
    EQUITY = "equity"
    CREDIT = "credit"
    MAGNITUDE = "magnitude"

    @property
    def label(self) -> str:
        return _CATEGORY_LABELS[self]


class Unit(StrEnum):
    MULTIPLE = "multiple"
    PERCENT = "percent"  # stored as a fraction: 0.052 means 5.2 %
    BASIS_POINTS = "basis_points"
    MILLIONS_EUR = "millions_eur"

    @property
    def symbol(self) -> str:
        return _UNIT_SYMBOLS[self]


def format_value(value: float, unit: Unit) -> str:
    """Value in Spanish notation with its unit: ``12,3x``, ``5,2 %``, ``45 pb``, ``1.234 M EUR``."""
    if unit is Unit.MULTIPLE:
        return f"{format_number(value, 1)}x"
    if unit is Unit.PERCENT:
        return f"{format_number(value * 100, 1)} %"
    if unit is Unit.BASIS_POINTS:
        return f"{format_number(value, 0)} pb"
    return f"{format_number(value, 0)} M EUR"


_CATEGORY_LABELS = {
    MetricCategory.EQUITY: "Renta variable",
    MetricCategory.CREDIT: "Crédito",
    MetricCategory.MAGNITUDE: "Magnitudes en euros",
}
_UNIT_SYMBOLS = {
    Unit.MULTIPLE: "x",
    Unit.PERCENT: "%",
    Unit.BASIS_POINTS: "pb",
    Unit.MILLIONS_EUR: "M EUR",
}


@dataclass(frozen=True)
class MetricResult:
    """A computed value with the inputs used, or the status and detail explaining its absence."""

    status: Status
    value: float | None = None
    detail: str | None = None
    inputs: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if (self.value is None) == (self.status is Status.OK):
            raise ValueError("A result has a value if and only if its status is OK")

    @classmethod
    def computed(
        cls, value: float, inputs: Mapping[str, float], detail: str | None = None
    ) -> MetricResult:
        return cls(Status.OK, value, detail, dict(inputs))

    @classmethod
    def unavailable(
        cls, status: Status, detail: str, inputs: Mapping[str, float] | None = None
    ) -> MetricResult:
        return cls(status, None, detail, dict(inputs or {}))

    @classmethod
    def from_figure(cls, figure: Figure) -> MetricResult:
        """Propagate the reason why an input is unavailable."""
        return cls.unavailable(figure.status, figure.explanation())

    @property
    def ok(self) -> bool:
        return self.status is Status.OK


def first_unavailable(*figures: Figure) -> MetricResult | None:
    """The first unavailable input as a result, or ``None`` when every input is available."""
    for figure in figures:
        if not figure.ok:
            return MetricResult.from_figure(figure)
    return None


def inputs_of(*figures: Figure) -> dict[str, float]:
    """Labels and values of available inputs, recorded with each result for traceability."""
    return {figure.label: figure.number() for figure in figures}


def divide(
    numerator: float,
    denominator: Figure,
    inputs: Mapping[str, float],
    *,
    unit: str = "",
) -> MetricResult:
    """``numerator / denominator``; a zero denominator is a division by zero and a negative one
    makes the ratio not meaningful (both are reported with the offending value)."""
    value = denominator.number()
    if value == 0:
        return MetricResult.unavailable(
            Status.DIVISION_BY_ZERO, f"{denominator.label} es cero", inputs
        )
    if value < 0:
        shown = f"{format_number(value)}{' ' + unit if unit else ''}"
        return MetricResult.unavailable(
            Status.NOT_MEANINGFUL, f"{denominator.label} es negativo ({shown})", inputs
        )
    return MetricResult.computed(numerator / value, inputs)


@dataclass(frozen=True)
class UniverseOutput:
    """Results of a metric computed across the universe: per issuer and per bond."""

    issuers: Mapping[str, MetricResult]
    bonds: Mapping[str, tuple[str, MetricResult]]  # ISIN -> (issuer id, result)


@dataclass(frozen=True, kw_only=True)
class MetricDefinition:
    """Documented definition of a metric. Texts are in Spanish: they feed docs/metricas.md."""

    metric_id: str
    name: str
    category: MetricCategory
    unit: Unit
    higher_is_better: bool | None  # None only for informative magnitudes
    description: str
    formula: str
    interpretation: str
    edge_cases: tuple[str, ...]
    excluded_industries: frozenset[Industry] = frozenset()
    exclusion_reason: str = ""


@dataclass(frozen=True, kw_only=True)
class CompanyMetric(MetricDefinition):
    """Metric computed from one company's snapshot."""

    compute: Callable[[CompanySnapshot, MetricsConfig], MetricResult]


@dataclass(frozen=True, kw_only=True)
class UniverseMetric(MetricDefinition):
    """Metric that needs the whole universe (for example, comparisons with peers)."""

    compute: Callable[[Sequence[CompanySnapshot], MetricsConfig], UniverseOutput]
