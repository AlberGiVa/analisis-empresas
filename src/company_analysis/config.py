"""Methodology configuration: normalisation limits, metric parameters, scores, screens and alerts.

The versioned YAML file (``config/analysis.yaml``) sets these values; the normalisation and metric
sections have documented defaults. Each run records the exact configuration it used.
"""

from collections import Counter
from enum import StrEnum
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveFloat,
    PositiveInt,
    model_validator,
)

from company_analysis.models import Sector
from company_analysis.models.identifiers import CountryCode
from company_analysis.models.ratings import RatingCode, rating_notch


class ConfigModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class NormalizationConfig(ConfigModel):
    """Maximum age of each kind of data at the analysis date (older data is flagged as stale)."""

    max_price_age_days: PositiveInt = 10
    max_quote_age_days: PositiveInt = 10
    max_fx_age_days: PositiveInt = 7
    max_financials_age_days: PositiveInt = 480


class RatingBucket(ConfigModel):
    """Group of ratings compared with each other, from the previous bucket down to ``worst``."""

    name: str = Field(min_length=1)
    worst: RatingCode


DEFAULT_RATING_BUCKETS = (
    RatingBucket(name="AAA-AA", worst="AA-"),
    RatingBucket(name="A", worst="A-"),
    RatingBucket(name="BBB", worst="BBB-"),
    RatingBucket(name="BB", worst="BB-"),
    RatingBucket(name="B", worst="B-"),
    RatingBucket(name="CCC o inferior", worst="D"),
)


class MetricsConfig(ConfigModel):
    notional_tax_rate: float = Field(default=0.25, ge=0, lt=1)
    min_bonds_per_rating_bucket: PositiveInt = 3
    rating_buckets: tuple[RatingBucket, ...] = DEFAULT_RATING_BUCKETS

    @model_validator(mode="after")
    def _buckets_cover_the_whole_scale(self) -> Self:
        notches = [rating_notch(bucket.worst) for bucket in self.rating_buckets]
        if not notches or notches != sorted(set(notches)) or notches[-1] != rating_notch("D"):
            raise ValueError(
                "Los tramos de rating deben ir de mejor a peor, sin repetirse, y el último "
                "debe llegar hasta D"
            )
        return self

    def bucket_for(self, rating: str) -> RatingBucket:
        """Bucket that contains ``rating``."""
        notch = rating_notch(rating)
        return next(b for b in self.rating_buckets if notch <= rating_notch(b.worst))


class ScoreType(StrEnum):
    EQUITY = "equity"
    CREDIT = "credit"

    @property
    def label(self) -> str:
        return "Renta variable" if self is ScoreType.EQUITY else "Crédito"


class FactorConfig(ConfigModel):
    metric: str = Field(min_length=1)
    weight: PositiveFloat


class ScoreModelConfig(ConfigModel):
    """Factors of a score and the minimum data needed to show it."""

    name: str = Field(min_length=1)
    factors: tuple[FactorConfig, ...] = Field(min_length=1)
    min_coverage: float = Field(gt=0, le=1)  # share of the applicable weight with data
    min_factors: PositiveInt  # factors with data

    @model_validator(mode="after")
    def _check_factors(self) -> Self:
        repeated = [m for m, n in Counter(f.metric for f in self.factors).items() if n > 1]
        if repeated:
            raise ValueError(f"{self.name}: factores repetidos: {', '.join(repeated)}")
        if self.min_factors > len(self.factors):
            raise ValueError(f"{self.name}: min_factors supera el número de factores")
        return self


class ScoringConfig(ConfigModel):
    min_peers: PositiveInt  # companies with data needed to compare within a sector (or universe)
    equity: ScoreModelConfig
    credit: ScoreModelConfig

    def model_for(self, score_type: ScoreType) -> ScoreModelConfig:
        return self.equity if score_type is ScoreType.EQUITY else self.credit


Operator = Literal["<", "<=", ">", ">="]


class ConditionConfig(ConfigModel):
    metric: str = Field(min_length=1)
    operator: Operator
    value: float


class ScreenConfig(ConfigModel):
    """Named filter: optional sector and country lists plus conditions on metrics."""

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=1)
    description: str = ""
    sectors: tuple[Sector, ...] = ()  # empty: every sector
    countries: tuple[CountryCode, ...] = ()  # empty: every country
    conditions: tuple[ConditionConfig, ...] = ()


class RatingDowngradeAlertConfig(ConfigModel):
    enabled: bool = True
    lookback_days: PositiveInt = 182


class LeverageAlertConfig(ConfigModel):
    enabled: bool = True
    max_net_debt_to_ebitda: PositiveFloat = 3.5


class ScoreChangeAlertConfig(ConfigModel):
    enabled: bool = True
    min_change_points: PositiveFloat = 15.0


class AlertsConfig(ConfigModel):
    rating_downgrade: RatingDowngradeAlertConfig = RatingDowngradeAlertConfig()
    leverage: LeverageAlertConfig = LeverageAlertConfig()
    score_change: ScoreChangeAlertConfig = ScoreChangeAlertConfig()


class AnalysisConfig(ConfigModel):
    """The whole methodology. ``version`` is set by hand; runs also record a content hash."""

    version: str = Field(min_length=1)
    normalization: NormalizationConfig = NormalizationConfig()
    metrics: MetricsConfig = MetricsConfig()
    scoring: ScoringConfig
    screens: tuple[ScreenConfig, ...] = ()
    alerts: AlertsConfig = AlertsConfig()

    @model_validator(mode="after")
    def _unique_screen_ids(self) -> Self:
        repeated = [i for i, n in Counter(s.id for s in self.screens).items() if n > 1]
        if repeated:
            raise ValueError(f"Filtros con el mismo id: {', '.join(repeated)}")
        return self

    def referenced_metrics(self) -> set[str]:
        """Metric ids used by scores and screens (they must exist in the registry)."""
        factors = {
            f.metric for model in (self.scoring.equity, self.scoring.credit) for f in model.factors
        }
        conditions = {c.metric for screen in self.screens for c in screen.conditions}
        return factors | conditions
