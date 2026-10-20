"""Common base class for domain models."""

from pydantic import BaseModel, ConfigDict


class DomainModel(BaseModel):
    """Immutable, strict-about-extra-fields base for every domain record."""

    model_config = ConfigDict(frozen=True, extra="forbid")
