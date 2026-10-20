"""Metric registry: every metric has an id, documented formula, unit, direction and applicability.

Importing this package registers all metrics (equity, credit and magnitudes in euros).
"""

from company_analysis.metrics import credit, equity, magnitudes
from company_analysis.metrics.base import (
    CompanyMetric,
    MetricCategory,
    MetricDefinition,
    MetricResult,
    Unit,
    UniverseMetric,
)
from company_analysis.metrics.registry import (
    EntityLevel,
    MetricRow,
    MetricTable,
    all_metrics,
    compute_metrics,
    get_metric,
)

__all__ = [
    "CompanyMetric",
    "EntityLevel",
    "MetricCategory",
    "MetricDefinition",
    "MetricResult",
    "MetricRow",
    "MetricTable",
    "Unit",
    "UniverseMetric",
    "all_metrics",
    "compute_metrics",
    "credit",
    "equity",
    "get_metric",
    "magnitudes",
]
