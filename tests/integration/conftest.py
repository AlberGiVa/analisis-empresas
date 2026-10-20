"""A database with the sample data and the two demo runs, shared by the integration tests."""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import duckdb
import pytest

from company_analysis.config_loader import load_config
from company_analysis.pipeline import run_analysis
from company_analysis.providers import SampleProvider
from company_analysis.providers.sample_generator import DEMO_AS_OF_DATES
from company_analysis.settings import PROJECT_ROOT
from company_analysis.storage import open_database, save_bundle


@dataclass(frozen=True)
class DemoDatabase:
    path: Path
    run_ids: tuple[str, str]  # previous and current analysis dates


@pytest.fixture(scope="session")
def demo_database(tmp_path_factory: pytest.TempPathFactory) -> DemoDatabase:
    path = tmp_path_factory.mktemp("demo") / "analysis.duckdb"
    config = load_config(PROJECT_ROOT / "config" / "analysis.yaml")
    with open_database(path) as conn:
        save_bundle(conn, SampleProvider(PROJECT_ROOT / "data" / "sample").fetch(), "sample")
        previous, current = (
            run_analysis(conn, as_of=as_of, config=config).record.run_id
            for as_of in DEMO_AS_OF_DATES
        )
    return DemoDatabase(path, (previous, current))


@pytest.fixture
def demo_conn(demo_database: DemoDatabase) -> Iterator[duckdb.DuckDBPyConnection]:
    with open_database(demo_database.path, read_only=True) as conn:
        yield conn
