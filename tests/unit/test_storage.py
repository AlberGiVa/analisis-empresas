"""Append-only storage and point-in-time reads (no look-ahead, reproducible cut-offs)."""

from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path

import duckdb
import pytest

from company_analysis.models import DataBundle, FinancialFact, FinancialItem
from company_analysis.providers import SampleProvider
from company_analysis.settings import PROJECT_ROOT
from company_analysis.storage import (
    list_load_batches,
    migrate,
    open_database,
    read_bundle,
    save_bundle,
)
from company_analysis.storage.database import MIGRATIONS_DIR
from tests import factories

FAR_FUTURE = datetime(2100, 1, 1)


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[duckdb.DuckDBPyConnection]:
    with open_database(tmp_path / "test.duckdb") as connection:
        yield connection


def bundle_with(*facts_: FinancialFact) -> DataBundle:
    return DataBundle(
        issuers=(factories.issuer(),),
        equities=(factories.equity(),),
        financial_facts=facts_,
    )


def revenue(conn: duckdb.DuckDBPyConnection, as_of: date, cutoff: datetime = FAR_FUTURE) -> float:
    facts = read_bundle(conn, as_of=as_of, cutoff=cutoff).financial_facts
    (value,) = [fact.value for fact in facts if fact.item is FinancialItem.REVENUE]
    return value


def count_rows(conn: duckdb.DuckDBPyConnection, table: str) -> int:
    row = conn.execute(f"SELECT count(*) FROM {table}").fetchone()
    assert row is not None
    return int(row[0])


def test_migrations_are_applied_once(tmp_path: Path) -> None:
    with open_database(tmp_path / "db.duckdb") as conn:
        assert migrate(conn) == []  # already applied when the database was opened
        assert count_rows(conn, "schema_migrations") == len(list(MIGRATIONS_DIR.glob("*.sql")))


def test_loading_the_same_content_twice_does_not_duplicate(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    bundle = bundle_with(factories.fact(FinancialItem.REVENUE, 100.0))
    first = save_bundle(conn, bundle, "test")
    second = save_bundle(conn, bundle, "test")
    assert first.created
    assert not second.created
    assert second.batch.load_id == first.batch.load_id
    assert count_rows(conn, "financial_facts") == 1


def test_values_are_invisible_before_their_publication_date(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    published = date(2025, 2, 15)
    save_bundle(conn, bundle_with(factories.fact(FinancialItem.REVENUE, 100.0)), "test")
    assert read_bundle(conn, as_of=date(2025, 2, 14), cutoff=FAR_FUTURE).financial_facts == ()
    assert revenue(conn, as_of=published) == 100.0


def test_a_restatement_replaces_the_original_only_once_published(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    original = factories.fact(FinancialItem.REVENUE, 100.0, published_at=date(2025, 2, 15))
    restated = factories.fact(FinancialItem.REVENUE, 110.0, published_at=date(2025, 9, 1))
    save_bundle(conn, bundle_with(original, restated), "test")
    assert revenue(conn, as_of=date(2025, 6, 30)) == 100.0
    assert revenue(conn, as_of=date(2025, 9, 1)) == 110.0


def test_a_later_load_corrects_a_value_without_overwriting_history(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    first_load, second_load = datetime(2025, 3, 1, 9), datetime(2025, 3, 5, 9)
    save_bundle(
        conn,
        bundle_with(factories.fact(FinancialItem.REVENUE, 100.0)),
        "test",
        loaded_at=first_load,
    )
    save_bundle(
        conn,
        bundle_with(factories.fact(FinancialItem.REVENUE, 105.0)),
        "test",
        loaded_at=second_load,
    )
    as_of = date(2025, 6, 30)
    assert revenue(conn, as_of, cutoff=first_load) == 100.0  # what was known at the first run
    assert revenue(conn, as_of, cutoff=second_load) == 105.0
    assert count_rows(conn, "financial_facts") == 2  # both versions are kept
    assert [batch.loaded_at for batch in list_load_batches(conn, until=first_load)] == [first_load]


def test_only_bonds_outstanding_at_the_analysis_date_are_read(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    matured = factories.bond(sequence=1, issued=date(2018, 1, 1), maturity=date(2025, 6, 30))
    future = factories.bond(sequence=2, issued=date(2026, 1, 10), maturity=date(2031, 1, 10))
    live = factories.bond(sequence=3, issued=date(2020, 1, 1), maturity=date(2030, 1, 1))
    bundle = DataBundle(
        issuers=(factories.issuer(),),
        equities=(factories.equity(),),
        bonds=(matured, future, live),
        bond_quotes=(
            factories.quote(matured.isin, date(2025, 6, 27), 120.0),
            factories.quote(live.isin, date(2025, 6, 27), 140.0),
        ),
        ratings=(
            factories.rating(matured.isin, "BBB", date(2018, 1, 1)),
            factories.rating(live.isin, "BBB", date(2020, 1, 1)),
        ),
    )
    save_bundle(conn, bundle, "test")
    visible = read_bundle(conn, as_of=date(2025, 12, 31), cutoff=FAR_FUTURE)
    assert [bond.isin for bond in visible.bonds] == [live.isin]
    assert {quote.isin for quote in visible.bond_quotes} == {live.isin}
    assert {rating.isin for rating in visible.ratings} == {live.isin}


def test_market_data_after_the_analysis_date_is_ignored(conn: duckdb.DuckDBPyConnection) -> None:
    bundle = DataBundle(
        issuers=(factories.issuer(),),
        equities=(factories.equity(),),
        equity_prices=(
            factories.price(date(2025, 6, 27), 10.0),
            factories.price(date(2025, 7, 4), 11.0),
        ),
        fx_rates=(
            factories.fx("USD", date(2025, 6, 30), 1.1),
            factories.fx("USD", date(2025, 7, 1), 1.2),
        ),
    )
    save_bundle(conn, bundle, "test")
    visible = read_bundle(conn, as_of=date(2025, 6, 30), cutoff=FAR_FUTURE)
    assert [price.close for price in visible.equity_prices] == [10.0]
    assert [rate.units_per_eur for rate in visible.fx_rates] == [1.1]


def test_the_sample_bundle_round_trips_through_the_database(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    bundle = SampleProvider(PROJECT_ROOT / "data" / "sample").fetch()
    save_bundle(conn, bundle, "sample")
    stored = read_bundle(conn, as_of=date(2026, 6, 30), cutoff=FAR_FUTURE)
    assert stored.row_counts()["issuers"] == 20
    assert stored.row_counts()["financial_facts"] == bundle.row_counts()["financial_facts"]
    assert set(stored.financial_facts) == set(bundle.financial_facts)
