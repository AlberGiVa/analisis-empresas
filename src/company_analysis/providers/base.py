"""Common interface for data providers."""

from abc import ABC, abstractmethod
from typing import ClassVar

from company_analysis.models import DataBundle


class DataProvider(ABC):
    """Source of reference, financial and market data.

    Real providers (Bloomberg, FactSet) will implement this same interface. ``fetch`` must return
    a self-contained bundle: every instrument, fact or quote refers to issuers and instruments
    included in the same bundle, and the bundle has passed validation.
    """

    name: ClassVar[str]

    @abstractmethod
    def fetch(self) -> DataBundle:
        """Return all the data the provider offers as a validated bundle."""
