"""The whole pipeline on the sample data: traceability, display rules, alerts, reproducibility."""

from collections import defaultdict
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import duckdb
import pytest

from company_analysis.config import ScoreType
from company_analysis.config_loader import LoadedConfig, load_config
from company_analysis.pipeline import AnalysisError, RunOutcome, run_analysis
from company_analysis.providers import SampleProvider
from company_analysis.providers.sample_generator import DEMO_AS_OF_DATES
from company_analysis.screening import AlertRule
from company_analysis.settings import PROJECT_ROOT
from company_analysis.storage import open_database, save_bundle
from company_analysis.storage.runs import RunStatus, list_runs, load_scores

PREVIOUS, CURRENT = DEMO_AS_OF_DATES


@pytest.fixture(scope="module")
def config() -> LoadedConfig:
    return load_config(PROJECT_ROOT / "config" / "analysis.yaml")


@pytest.fixture(scope="module")
def conn(tmp_path_factory: pytest.TempPathFactory) -> Iterator[duckdb.DuckDBPyConnection]:
    path = tmp_path_factory.mktemp("pipeline") / "analysis.duckdb"
    with open_database(path) as connection:
        save_bundle(connection, SampleProvider(PROJECT_ROOT / "data" / "sample").fetch(), "sample")
        yield connection


@pytest.fixture(scope="module")
def runs(conn: duckdb.DuckDBPyConnection, config: LoadedConfig) -> tuple[RunOutcome, RunOutcome]:
    previous = run_analysis(conn, as_of=PREVIOUS, config=config)
    current = run_analysis(conn, as_of=CURRENT, config=config)
    return previous, current


def test_every_run_is_recorded_with_its_data_and_configuration(
    conn: duckdb.DuckDBPyConnection, runs: tuple[RunOutcome, RunOutcome], config: LoadedConfig
) -> None:
    recorded = {record.run_id: record for record in list_runs(conn)}
    for outcome in runs:
        record = recorded[outcome.record.run_id]
        assert record.status is RunStatus.COMPLETED
        assert record.config_version == config.version
        assert record.config_hash == config.content_hash
        assert record.config_snapshot == config.text
        assert len(record.load_ids) == 1
        assert record.data_cutoff == record.started_at
    assert [recorded[r.record.run_id].as_of_date for r in runs] == [PREVIOUS, CURRENT]


def test_alerts_of_the_current_run(runs: tuple[RunOutcome, RunOutcome]) -> None:
    issuers_by_rule: dict[AlertRule, set[str]] = defaultdict(set)
    for alert in runs[1].alerts:
        issuers_by_rule[alert.rule].add(alert.issuer_id)
    assert issuers_by_rule[AlertRule.RATING_DOWNGRADE] == {"ASHC"}
    assert {"ASHC", "GRSH", "LUMB", "ORBE"} <= issuers_by_rule[AlertRule.LEVERAGE]
    changes = [a for a in runs[1].alerts if a.rule is AlertRule.SCORE_CHANGE]
    assert changes  # the previous run exists
    assert {a.details["ejecucion_anterior"] for a in changes} == {runs[0].record.run_id}


def test_no_downgrade_alert_before_the_downgrade(runs: tuple[RunOutcome, RunOutcome]) -> None:
    rules = {alert.rule for alert in runs[0].alerts}
    assert AlertRule.RATING_DOWNGRADE not in rules
    assert AlertRule.SCORE_CHANGE not in rules  # there is no earlier run


def test_scores_follow_the_display_rules(runs: tuple[RunOutcome, RunOutcome]) -> None:
    scores = {(s.issuer_id, s.score_type): s for s in runs[1].scores}
    stale = scores[("SKRV", ScoreType.EQUITY)]
    assert not stale.displayed
    assert stale.reason is not None
    assert stale.reason.startswith("Cobertura")
    for bank in ("BVAL", "WESB", "AUBR"):
        assert scores[(bank, ScoreType.EQUITY)].displayed
        credit = scores[(bank, ScoreType.CREDIT)]
        assert not credit.displayed
        assert credit.reason is not None
        assert credit.reason.startswith("Solo 1 factor")
    assert scores[("HELV", ScoreType.CREDIT)].displayed  # no debt, but enough factors
    for score in runs[1].scores:
        if score.value is not None:
            assert 0 <= score.value <= 100
            assert sum(c.contribution or 0.0 for c in score.components) == pytest.approx(
                score.value
            )


def test_stored_scores_match_the_computed_ones(
    conn: duckdb.DuckDBPyConnection, runs: tuple[RunOutcome, RunOutcome]
) -> None:
    stored = {(s.issuer_id, s.score_type): s for s in load_scores(conn, runs[1].record.run_id)}
    computed = {(s.issuer_id, s.score_type): s for s in runs[1].scores}
    assert stored == computed


def test_running_again_with_the_same_data_gives_the_same_results(
    conn: duckdb.DuckDBPyConnection, runs: tuple[RunOutcome, RunOutcome], config: LoadedConfig
) -> None:
    again = run_analysis(conn, as_of=CURRENT, config=config)
    assert again.record.run_id != runs[1].record.run_id  # a new run, nothing is overwritten
    values = {(s.issuer_id, s.score_type): s.value for s in again.scores}
    assert values == {(s.issuer_id, s.score_type): s.value for s in runs[1].scores}
    assert [a.message for a in again.alerts] == [a.message for a in runs[1].alerts]


def test_data_loaded_after_the_run_started_is_not_used(
    tmp_path: Path, config: LoadedConfig
) -> None:
    with open_database(tmp_path / "late.duckdb") as conn:
        bundle = SampleProvider(PROJECT_ROOT / "data" / "sample").fetch()
        save_bundle(conn, bundle, "sample", loaded_at=datetime(2026, 7, 1, 9))
        with pytest.raises(AnalysisError, match="No hay datos cargados"):
            run_analysis(conn, as_of=CURRENT, config=config, started_at=datetime(2026, 6, 30, 18))


def test_a_failed_run_is_recorded(tmp_path: Path, config: LoadedConfig) -> None:
    with open_database(tmp_path / "empty.duckdb") as conn:
        with pytest.raises(AnalysisError):
            run_analysis(conn, as_of=CURRENT, config=config)
        (record,) = list_runs(conn)
    assert record.status is RunStatus.FAILED
    assert record.error is not None
    assert "No hay datos cargados" in record.error
