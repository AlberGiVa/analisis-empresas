from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path

import duckdb
import pytest

from company_analysis.metrics import MetricTable
from company_analysis.storage import open_database
from company_analysis.storage.runs import (
    RunRecord,
    RunStatus,
    get_run,
    list_runs,
    previous_scores,
    save_failed_run,
    save_run,
)


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[duckdb.DuckDBPyConnection]:
    with open_database(tmp_path / "runs.duckdb") as connection:
        yield connection


def record(run_id: str, as_of: date, status: RunStatus = RunStatus.COMPLETED) -> RunRecord:
    started = datetime(2026, 10, 20, 9, int(run_id[-1]))
    return RunRecord(
        run_id=run_id,
        started_at=started,
        finished_at=started,
        as_of_date=as_of,
        data_cutoff=started,
        load_ids=("L1",),
        config_version="v1",
        config_hash="abc",
        config_snapshot="version: v1",
        code_version="0.1.0",
        git_commit=None,
        triggered_by="prueba",
        status=status,
        error=None if status is RunStatus.COMPLETED else "fallo de prueba",
    )


def save(conn: duckdb.DuckDBPyConnection, run: RunRecord) -> None:
    if run.status is RunStatus.COMPLETED:
        save_run(conn, run, MetricTable([]), [], [], [])
    else:
        save_failed_run(conn, run)


def test_runs_are_listed_in_order_and_read_back(conn: duckdb.DuckDBPyConnection) -> None:
    first, second = record("R1", date(2025, 12, 31)), record("R2", date(2026, 6, 30))
    save(conn, first)
    save(conn, second)
    assert list_runs(conn) == [first, second]
    assert get_run(conn, "R2") == second
    assert get_run(conn, "R9") is None


def test_previous_run_is_the_latest_completed_one_with_an_earlier_date(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    save(conn, record("R1", date(2025, 12, 31)))
    save(conn, record("R2", date(2026, 3, 31), RunStatus.FAILED))
    save(conn, record("R3", date(2026, 6, 30)))
    before_june = previous_scores(conn, date(2026, 6, 30))
    assert before_june is not None
    assert before_june.run_id == "R1"  # the failed run is ignored
    after = previous_scores(conn, date(2027, 1, 1))
    assert after is not None
    assert after.run_id == "R3"
    assert previous_scores(conn, date(2025, 12, 31)) is None
