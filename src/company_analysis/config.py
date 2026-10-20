"""Methodology configuration: normalisation limits and metric parameters.

Every value has a documented default. The versioned YAML file (``config/analysis.yaml``) can
override them, and each run records the exact configuration it used.
"""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, model_validator

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
