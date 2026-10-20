"""Contract that every data provider must fulfil. Add new providers to ``PROVIDER_FACTORIES``."""

from collections import Counter
from collections.abc import Callable
from pathlib import Path

import pytest

from company_analysis.models import DataBundle
from company_analysis.providers import DataProvider, SampleProvider, create_provider
from company_analysis.providers.workbook import WorkbookProvider, write_workbook
from company_analysis.settings import PROJECT_ROOT, Settings

SAMPLE_DIR = PROJECT_ROOT / "data" / "sample"


def workbook_provider(directory: Path) -> DataProvider:
    """The Excel import, fed with a workbook that contains the sample data."""
    path = write_workbook(SampleProvider(SAMPLE_DIR).fetch(), directory / "datos.xlsx")
    return WorkbookProvider(path)


# Each factory receives an empty temporary folder for any files it needs.
PROVIDER_FACTORIES: dict[str, Callable[[Path], DataProvider]] = {
    "sample": lambda _directory: SampleProvider(SAMPLE_DIR),
    "workbook": workbook_provider,
}


@pytest.fixture(params=sorted(PROVIDER_FACTORIES))
def provider(request: pytest.FixtureRequest, tmp_path: Path) -> DataProvider:
    factory: Callable[[Path], DataProvider] = PROVIDER_FACTORIES[request.param]
    return factory(tmp_path)


def test_fetch_returns_a_validated_bundle(provider: DataProvider) -> None:
    bundle = provider.fetch()
    assert isinstance(bundle, DataBundle)
    assert bundle.issuers


def test_every_issuer_has_exactly_one_listed_share(provider: DataProvider) -> None:
    bundle = provider.fetch()
    listings = Counter(equity.issuer_id for equity in bundle.equities)
    assert {issuer.issuer_id: listings[issuer.issuer_id] for issuer in bundle.issuers} == {
        issuer.issuer_id: 1 for issuer in bundle.issuers
    }


def test_provider_has_a_stable_name(provider: DataProvider) -> None:
    assert provider.name


def test_providers_are_created_by_their_cli_name() -> None:
    settings = Settings(_env_file=None)
    assert isinstance(create_provider("ejemplo", settings), SampleProvider)
    with pytest.raises(KeyError):
        create_provider("bloomberg", settings)
