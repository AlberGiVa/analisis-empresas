"""Equity and credit scores (0-100): weighted average of factor percentiles, fully decomposed.

For each factor, a company is compared with the companies of its sector that have a value for
that factor; if there are fewer than ``min_peers``, with the whole universe. Weights are spread
over the factors with data. Coverage is the weight with data over the weight of the factors that
apply to the company; below the minimum coverage, or with too few factors, the score is not shown.
"""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum

from company_analysis.config import FactorConfig, ScoreModelConfig, ScoreType, ScoringConfig
from company_analysis.figures import Status
from company_analysis.formatting import format_number
from company_analysis.metrics import MetricTable, get_metric
from company_analysis.models import Sector
from company_analysis.normalization import CompanySnapshot
from company_analysis.scoring.percentiles import percentile_ranks


class ReferenceGroup(StrEnum):
    SECTOR = "sector"
    UNIVERSE = "universe"

    @property
    def label(self) -> str:
        return "Sector" if self is ReferenceGroup.SECTOR else "Universo"


@dataclass(frozen=True)
class ScoreComponent:
    """One factor of a score: its value, how it compares and how much it contributes."""

    metric_id: str
    weight: float
    status: Status  # OK when the factor has a percentile
    value: float | None = None
    detail: str | None = None
    reference_group: ReferenceGroup | None = None
    peer_count: int | None = None
    percentile: float | None = None
    contribution: float | None = None  # points of the score; they add up to the score

    @property
    def applies(self) -> bool:
        return self.status is not Status.NOT_APPLICABLE


@dataclass(frozen=True)
class Score:
    issuer_id: str
    score_type: ScoreType
    value: float | None  # None when the score is not shown
    coverage: float
    factors_with_data: int
    displayed: bool
    reason: str | None  # why the score is not shown
    components: tuple[ScoreComponent, ...]


@dataclass(frozen=True)
class _PeerRank:
    group: ReferenceGroup | None
    peer_count: int
    percentile: float | None


def _factor_ranks(
    metric_id: str, sectors: Mapping[str, Sector], metrics: MetricTable, min_peers: int
) -> dict[str, _PeerRank]:
    """Rank of every company with a value, within its sector or, if too small, the universe."""
    higher_is_better = get_metric(metric_id).higher_is_better
    if higher_is_better is None:
        raise ValueError(f"La métrica {metric_id} no tiene sentido preferido: no puede puntuar")
    values: dict[str, float] = {}
    for issuer_id in sectors:
        value = metrics.result(issuer_id, metric_id).value
        if value is not None:
            values[issuer_id] = value
    by_sector: dict[Sector, dict[str, float]] = defaultdict(dict)
    for issuer_id, value in values.items():
        by_sector[sectors[issuer_id]][issuer_id] = value
    sector_ranks = {
        sector: percentile_ranks(group, higher_is_better=higher_is_better)
        for sector, group in by_sector.items()
        if len(group) >= min_peers
    }
    universe_ranks = (
        percentile_ranks(values, higher_is_better=higher_is_better)
        if len(values) >= min_peers
        else None
    )
    ranks = {}
    for issuer_id in values:
        sector = sectors[issuer_id]
        if sector in sector_ranks:
            ranks[issuer_id] = _PeerRank(
                ReferenceGroup.SECTOR, len(by_sector[sector]), sector_ranks[sector][issuer_id]
            )
        elif universe_ranks is not None:
            ranks[issuer_id] = _PeerRank(
                ReferenceGroup.UNIVERSE, len(values), universe_ranks[issuer_id]
            )
        else:
            ranks[issuer_id] = _PeerRank(None, len(values), None)
    return ranks


def _component(
    issuer_id: str,
    factor: FactorConfig,
    metrics: MetricTable,
    ranks: Mapping[str, _PeerRank],
    min_peers: int,
) -> ScoreComponent:
    result = metrics.result(issuer_id, factor.metric)
    if result.value is None:
        return ScoreComponent(factor.metric, factor.weight, result.status, detail=result.detail)
    rank = ranks[issuer_id]
    if rank.percentile is None:
        return ScoreComponent(
            factor.metric,
            factor.weight,
            Status.INSUFFICIENT_PEERS,
            value=result.value,
            detail=f"solo {rank.peer_count} empresas con dato (mínimo {min_peers})",
            peer_count=rank.peer_count,
        )
    return ScoreComponent(
        factor.metric,
        factor.weight,
        Status.OK,
        value=result.value,
        detail=result.detail,
        reference_group=rank.group,
        peer_count=rank.peer_count,
        percentile=rank.percentile,
    )


def _percent(fraction: float) -> str:
    return f"{format_number(fraction * 100, 0)} %"


def _aggregate(
    issuer_id: str,
    score_type: ScoreType,
    model: ScoreModelConfig,
    components: list[ScoreComponent],
) -> Score:
    applicable = [c for c in components if c.applies]
    usable = [c for c in applicable if c.percentile is not None]
    applicable_weight = sum(c.weight for c in applicable)
    usable_weight = sum(c.weight for c in usable)
    coverage = usable_weight / applicable_weight if applicable_weight else 0.0
    reasons = []
    if not applicable:
        reasons.append("ningún factor aplica a esta empresa")
    else:
        if coverage < model.min_coverage:
            reasons.append(
                f"cobertura del {_percent(coverage)}, inferior al mínimo del "
                f"{_percent(model.min_coverage)}"
            )
        if len(usable) < model.min_factors:
            factors = "factor" if len(usable) == 1 else "factores"
            reasons.append(f"solo {len(usable)} {factors} con dato (mínimo {model.min_factors})")
    if reasons:
        reason = "; ".join(reasons)
        return Score(
            issuer_id,
            score_type,
            None,
            coverage,
            len(usable),
            displayed=False,
            reason=reason[0].upper() + reason[1:],
            components=tuple(components),
        )
    contributions = {
        c.metric_id: c.weight * c.percentile / usable_weight
        for c in usable
        if c.percentile is not None
    }
    final = tuple(
        replace(c, contribution=contributions[c.metric_id]) if c.metric_id in contributions else c
        for c in components
    )
    return Score(
        issuer_id,
        score_type,
        sum(contributions.values()),
        coverage,
        len(usable),
        displayed=True,
        reason=None,
        components=final,
    )


def compute_scores(
    snapshots: Sequence[CompanySnapshot], metrics: MetricTable, config: ScoringConfig
) -> list[Score]:
    """Equity and credit score of every company, with their breakdown by factor."""
    sectors = {snapshot.issuer_id: snapshot.issuer.sector for snapshot in snapshots}
    scores = []
    for score_type in ScoreType:
        model = config.model_for(score_type)
        ranks = {
            factor.metric: _factor_ranks(factor.metric, sectors, metrics, config.min_peers)
            for factor in model.factors
        }
        for issuer_id in sectors:
            components = [
                _component(issuer_id, factor, metrics, ranks[factor.metric], config.min_peers)
                for factor in model.factors
            ]
            scores.append(_aggregate(issuer_id, score_type, model, components))
    return scores
