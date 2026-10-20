"""Equity and credit scores built from sector-relative percentiles."""

from company_analysis.scoring.percentiles import percentile_ranks
from company_analysis.scoring.scores import (
    ReferenceGroup,
    Score,
    ScoreComponent,
    compute_scores,
)

__all__ = ["ReferenceGroup", "Score", "ScoreComponent", "compute_scores", "percentile_ranks"]
