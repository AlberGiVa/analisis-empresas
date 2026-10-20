"""Central metric registry and the computation of every metric for a set of snapshots."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from company_analysis.config import MetricsConfig
from company_analysis.figures import Status
from company_analysis.metrics.base import (
    CompanyMetric,
    MetricCategory,
    MetricDefinition,
    MetricResult,
    UniverseMetric,
)
from company_analysis.normalization import CompanySnapshot

_REGISTRY: dict[str, MetricDefinition] = {}


def register[M: MetricDefinition](definition: M) -> M:
    """Add a metric to the registry after checking that its definition is complete."""
    if definition.metric_id in _REGISTRY:
        raise ValueError(f"Métrica duplicada: {definition.metric_id}")
    if (definition.higher_is_better is None) != (definition.category is MetricCategory.MAGNITUDE):
        raise ValueError(f"{definition.metric_id}: solo las magnitudes no tienen sentido preferido")
    if definition.excluded_industries and not definition.exclusion_reason:
        raise ValueError(f"{definition.metric_id}: falta el motivo de la exclusión")
    _REGISTRY[definition.metric_id] = definition
    return definition


def all_metrics() -> list[MetricDefinition]:
    """Every registered metric, in registration order."""
    return list(_REGISTRY.values())


def get_metric(metric_id: str) -> MetricDefinition:
    try:
        return _REGISTRY[metric_id]
    except KeyError:
        raise KeyError(f"Métrica desconocida: {metric_id}") from None


class EntityLevel(StrEnum):
    ISSUER = "issuer"
    BOND = "bond"


@dataclass(frozen=True)
class MetricRow:
    metric_id: str
    issuer_id: str
    level: EntityLevel
    entity_id: str  # the issuer id, or the ISIN of a bond
    result: MetricResult


class MetricTable:
    """Results of one computation, with lookups by issuer and metric."""

    def __init__(self, rows: Iterable[MetricRow]) -> None:
        self.rows = tuple(rows)
        self._by_issuer = {
            (row.issuer_id, row.metric_id): row.result
            for row in self.rows
            if row.level is EntityLevel.ISSUER
        }

    def result(self, issuer_id: str, metric_id: str) -> MetricResult:
        return self._by_issuer[(issuer_id, metric_id)]

    def bond_rows(self, metric_id: str) -> list[MetricRow]:
        return [
            row for row in self.rows if row.level is EntityLevel.BOND and row.metric_id == metric_id
        ]


def compute_metrics(snapshots: Sequence[CompanySnapshot], config: MetricsConfig) -> MetricTable:
    """Compute every registered metric for every company (and bond, where applicable)."""
    rows: list[MetricRow] = []
    for definition in all_metrics():
        not_applicable = MetricResult.unavailable(
            Status.NOT_APPLICABLE, definition.exclusion_reason or "No aplica"
        )
        universe = (
            definition.compute(snapshots, config)
            if isinstance(definition, UniverseMetric)
            else None
        )
        for snapshot in snapshots:
            if snapshot.issuer.industry in definition.excluded_industries:
                result = not_applicable
            elif isinstance(definition, CompanyMetric):
                result = definition.compute(snapshot, config)
            else:
                assert universe is not None
                result = universe.issuers[snapshot.issuer_id]
            rows.append(
                MetricRow(
                    definition.metric_id,
                    snapshot.issuer_id,
                    EntityLevel.ISSUER,
                    snapshot.issuer_id,
                    result,
                )
            )
        if universe is not None:
            rows.extend(
                MetricRow(definition.metric_id, issuer_id, EntityLevel.BOND, isin, result)
                for isin, (issuer_id, result) in universe.bonds.items()
            )
    return MetricTable(rows)
