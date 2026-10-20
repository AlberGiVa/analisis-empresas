"""Data providers: a common interface and the available implementations."""

from collections.abc import Callable

from company_analysis.providers.base import DataProvider
from company_analysis.providers.sample import SampleProvider
from company_analysis.settings import Settings

# Name used in the CLI (Spanish, user interface) -> factory.
PROVIDERS: dict[str, Callable[[Settings], DataProvider]] = {
    "ejemplo": lambda settings: SampleProvider(settings.sample_data_dir),
}


def create_provider(name: str, settings: Settings) -> DataProvider:
    """Instantiate a provider by its CLI name. Raises ``KeyError`` if it does not exist."""
    return PROVIDERS[name](settings)


__all__ = ["PROVIDERS", "DataProvider", "SampleProvider", "create_provider"]
