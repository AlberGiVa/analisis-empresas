"""Scores: sector or universe percentiles, coverage, display rules and breakdown."""

import pytest

from company_analysis.config import (
    FactorConfig,
    ScoreModelConfig,
    ScoreType,
    ScoringConfig,
)
from company_analysis.figures import Status
from company_analysis.metrics import EntityLevel, MetricResult, MetricRow, MetricTable
from company_analysis.models import Industry
from company_analysis.normalization import CompanySnapshot
from company_analysis.scoring import ReferenceGroup, Score, compute_scores
from tests import factories
from tests.snapshots import snapshot

INDUSTRIALS = ("AA", "BB", "CC")
TECHNOLOGY = ("DD", "EE")

# pe_ratio: lower is better; roe: higher is better
VALUES: dict[tuple[str, str], float | Status] = {
    ("AA", "pe_ratio"): 10.0,
    ("BB", "pe_ratio"): 20.0,
    ("CC", "pe_ratio"): 30.0,
    ("DD", "pe_ratio"): 15.0,
    ("EE", "pe_ratio"): 25.0,
    ("AA", "roe"): 0.10,
    ("BB", "roe"): 0.20,
    ("CC", "roe"): Status.MISSING,
    ("DD", "roe"): 0.30,
    ("EE", "roe"): Status.NOT_APPLICABLE,
}


def companies() -> list[CompanySnapshot]:
    return [
        snapshot(issuer=factories.issuer(issuer_id, industry=Industry.CAPITAL_GOODS))
        for issuer_id in INDUSTRIALS
    ] + [
        snapshot(issuer=factories.issuer(issuer_id, industry=Industry.SOFTWARE))
        for issuer_id in TECHNOLOGY
    ]


def metric_table(values: dict[tuple[str, str], float | Status]) -> MetricTable:
    rows = []
    for (issuer_id, metric_id), value in values.items():
        result = (
            MetricResult.unavailable(value, "motivo de prueba")
            if isinstance(value, Status)
            else MetricResult.computed(value, {})
        )
        rows.append(MetricRow(metric_id, issuer_id, EntityLevel.ISSUER, issuer_id, result))
    return MetricTable(rows)


def scoring(
    min_coverage: float = 0.5,
    min_factors: int = 1,
    min_peers: int = 3,
    required: tuple[str, ...] = (),
) -> ScoringConfig:
    model = ScoreModelConfig(
        name="Prueba",
        factors=(FactorConfig(metric="pe_ratio", weight=1), FactorConfig(metric="roe", weight=1)),
        min_coverage=min_coverage,
        min_factors=min_factors,
        required_factors=required,
    )
    return ScoringConfig(min_peers=min_peers, equity=model, credit=model)


def equity_scores(
    config: ScoringConfig, values: dict[tuple[str, str], float | Status] = VALUES
) -> dict[str, Score]:
    scores = compute_scores(companies(), metric_table(values), config)
    return {s.issuer_id: s for s in scores if s.score_type is ScoreType.EQUITY}


def test_hand_calculated_scores() -> None:
    scores = equity_scores(scoring())
    # PER within industrials (3 >= min_peers): A 83.3, B 50, C 16.7.
    # PER of technology (2 < 3) against the universe of 5: D 70, E 30.
    # ROE: only 3 values in the whole universe: A 16.7, B 50, D 83.3.
    assert scores["AA"].value == pytest.approx((250 / 3 + 50 / 3) / 2)  # 50.0
    assert scores["BB"].value == pytest.approx(50.0)
    assert scores["CC"].value == pytest.approx(50 / 3)  # only PER has data
    assert scores["DD"].value == pytest.approx((70 + 250 / 3) / 2)
    assert scores["EE"].value == pytest.approx(30.0)  # ROE does not apply


def test_the_breakdown_explains_each_factor() -> None:
    scores = equity_scores(scoring())
    pe_a = scores["AA"].components[0]
    assert (pe_a.reference_group, pe_a.peer_count) == (ReferenceGroup.SECTOR, 3)
    pe_d = scores["DD"].components[0]
    assert (pe_d.reference_group, pe_d.peer_count) == (ReferenceGroup.UNIVERSE, 5)
    for score in scores.values():
        assert score.value is not None
        total = sum(c.contribution or 0.0 for c in score.components)
        assert total == pytest.approx(score.value)


def test_coverage_counts_only_the_factors_that_apply() -> None:
    scores = equity_scores(scoring())
    assert scores["CC"].coverage == pytest.approx(0.5)  # ROE is missing
    assert scores["EE"].coverage == pytest.approx(1.0)  # ROE does not apply
    roe_e = scores["EE"].components[1]
    assert roe_e.status is Status.NOT_APPLICABLE


def test_a_score_below_the_minimum_coverage_is_not_shown() -> None:
    scores = equity_scores(scoring(min_coverage=0.6))
    hidden = scores["CC"]
    assert not hidden.displayed
    assert hidden.value is None
    assert hidden.reason == "Cobertura del 50 %, inferior al mínimo del 60 %"
    assert all(c.contribution is None for c in hidden.components)


def test_a_score_with_too_few_factors_is_not_shown() -> None:
    scores = equity_scores(scoring(min_factors=2))
    assert not scores["EE"].displayed
    assert scores["EE"].reason == "Solo 1 factor con dato (mínimo 2)"
    assert scores["AA"].displayed


def test_without_enough_peers_in_the_universe_the_factor_has_no_percentile() -> None:
    scores = equity_scores(scoring(min_peers=4))
    roe_a = scores["AA"].components[1]  # only 3 companies have ROE
    assert roe_a.status is Status.INSUFFICIENT_PEERS
    assert roe_a.percentile is None
    assert scores["AA"].coverage == pytest.approx(0.5)


def test_a_company_to_which_no_factor_applies() -> None:
    values = dict(VALUES)
    values[("EE", "pe_ratio")] = Status.NOT_APPLICABLE
    scores = equity_scores(scoring(), values)
    assert not scores["EE"].displayed
    assert scores["EE"].reason == "Ningún factor aplica a esta empresa"


def test_a_required_factor_that_does_not_apply_leaves_the_company_without_score() -> None:
    scores = equity_scores(scoring(required=("roe",)))
    excluded = scores["EE"]  # ROE does not apply to it
    assert not excluded.displayed
    assert excluded.value is None
    assert excluded.reason == "Motivo de prueba (factor obligatorio: ROE)"
    assert scores["CC"].displayed  # ROE applies but is missing: the coverage rules decide
