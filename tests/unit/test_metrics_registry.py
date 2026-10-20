"""The metric registry: complete documentation, applicability and docs/metricas.md in sync."""

import pytest

from company_analysis.config import MetricsConfig
from company_analysis.figures import Status
from company_analysis.metrics import (
    MetricCategory,
    MetricDefinition,
    all_metrics,
    compute_metrics,
    get_metric,
)
from company_analysis.metrics.documentation import render_metrics_markdown
from company_analysis.metrics.registry import register
from company_analysis.models import FinancialItem as Item
from company_analysis.models import Industry
from company_analysis.settings import PROJECT_ROOT
from tests import factories
from tests.snapshots import snapshot

EQUITY = {
    "pe_ratio",
    "ev_to_ebitda",
    "fcf_yield",
    "roe",
    "roic",
    "ebitda_margin",
    "revenue_growth",
}
CREDIT = {"net_debt_to_ebitda", "interest_coverage", "debt_to_equity", "spread_vs_rating_bucket"}


def test_registry_contains_the_metrics_of_the_brief() -> None:
    by_category = {
        category: {m.metric_id for m in all_metrics() if m.category is category}
        for category in MetricCategory
    }
    assert by_category[MetricCategory.EQUITY] == EQUITY
    assert by_category[MetricCategory.CREDIT] == CREDIT
    assert len(by_category[MetricCategory.MAGNITUDE]) == 5


@pytest.mark.parametrize("metric", all_metrics(), ids=lambda metric: metric.metric_id)
def test_every_metric_is_fully_documented(metric: MetricDefinition) -> None:
    assert metric.name
    assert metric.description
    assert metric.formula
    assert metric.interpretation
    assert metric.edge_cases
    if metric.excluded_industries:
        assert metric.exclusion_reason


def test_metrics_cannot_be_registered_twice() -> None:
    with pytest.raises(ValueError, match="duplicada"):
        register(get_metric("pe_ratio"))


def test_banks_and_insurers_get_not_applicable_with_its_reason() -> None:
    bank = snapshot(
        issuer=factories.issuer("BANK", industry=Industry.BANKS),
        market_cap=900.0,
        flows={Item.NET_INCOME: 100.0, Item.EBITDA: 300.0},
        stocks={Item.TOTAL_DEBT: 5000.0, Item.CASH: 100.0, Item.TOTAL_EQUITY: 1200.0},
    )
    table = compute_metrics([bank], MetricsConfig())
    for metric_id in (
        "ev_to_ebitda",
        "fcf_yield",
        "roic",
        "ebitda_margin",
        "net_debt_to_ebitda",
        "interest_coverage",
        "debt_to_equity",
    ):
        result = table.result("BANK", metric_id)
        assert result.status is Status.NOT_APPLICABLE, metric_id
        assert result.detail is not None
        assert "bancos y aseguradoras" in result.detail
    assert table.result("BANK", "pe_ratio").value == pytest.approx(9.0)


def test_metrics_dictionary_is_up_to_date() -> None:
    path = PROJECT_ROOT / "docs" / "metricas.md"
    assert path.read_text(encoding="utf-8") == render_metrics_markdown(), (
        "docs/metricas.md no está al día: ejecuta uv run python scripts/generate_metrics_doc.py"
    )
