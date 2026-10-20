"""Storage of analysis runs: the run record (traceability) and all its outputs."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any

import duckdb

from company_analysis.config import ScoreType
from company_analysis.figures import Status
from company_analysis.metrics import EntityLevel, MetricResult, MetricRow, MetricTable
from company_analysis.scoring import ReferenceGroup, Score, ScoreComponent
from company_analysis.screening import (
    Alert,
    AlertRule,
    ConditionResult,
    PreviousScores,
    ScreenOutcome,
    ScreenResult,
)
from company_analysis.storage.database import insert_rows


class RunStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"

    @property
    def label(self) -> str:
        return "Completada" if self is RunStatus.COMPLETED else "Fallida"


@dataclass(frozen=True)
class RunRecord:
    """Everything needed to know what a run did and to reproduce it."""

    run_id: str
    started_at: datetime
    finished_at: datetime
    as_of_date: date
    data_cutoff: datetime
    load_ids: tuple[str, ...]
    config_version: str
    config_hash: str
    config_snapshot: str
    code_version: str
    git_commit: str | None
    triggered_by: str
    status: RunStatus
    error: str | None = None


_RUN_COLUMNS = (
    "run_id, started_at, finished_at, as_of_date, data_cutoff, load_ids, config_version, "
    "config_hash, config_snapshot, code_version, git_commit, triggered_by, status, error"
)


def _run_row(record: RunRecord) -> dict[str, object]:
    return {
        "run_id": record.run_id,
        "started_at": record.started_at,
        "finished_at": record.finished_at,
        "as_of_date": record.as_of_date,
        "data_cutoff": record.data_cutoff,
        "load_ids": json.dumps(list(record.load_ids)),
        "config_version": record.config_version,
        "config_hash": record.config_hash,
        "config_snapshot": record.config_snapshot,
        "code_version": record.code_version,
        "git_commit": record.git_commit,
        "triggered_by": record.triggered_by,
        "status": record.status.value,
        "error": record.error,
    }


def _record_from_row(row: tuple[Any, ...]) -> RunRecord:
    values = dict(zip([c.strip() for c in _RUN_COLUMNS.split(",")], row, strict=True))
    return RunRecord(
        run_id=values["run_id"],
        started_at=values["started_at"],
        finished_at=values["finished_at"],
        as_of_date=values["as_of_date"],
        data_cutoff=values["data_cutoff"],
        load_ids=tuple(json.loads(values["load_ids"])),
        config_version=values["config_version"],
        config_hash=values["config_hash"],
        config_snapshot=values["config_snapshot"],
        code_version=values["code_version"],
        git_commit=values["git_commit"],
        triggered_by=values["triggered_by"],
        status=RunStatus(values["status"]),
        error=values["error"],
    )


def _component_row(run_id: str, score: Score, component: ScoreComponent) -> dict[str, object]:
    return {
        "run_id": run_id,
        "issuer_id": score.issuer_id,
        "score_type": score.score_type.value,
        "metric_id": component.metric_id,
        "weight": component.weight,
        "status": component.status.value,
        "value": component.value,
        "detail": component.detail,
        "reference_group": component.reference_group.value if component.reference_group else None,
        "peer_count": component.peer_count,
        "percentile": component.percentile,
        "contribution": component.contribution,
    }


def save_run(
    conn: duckdb.DuckDBPyConnection,
    record: RunRecord,
    metrics: MetricTable,
    scores: Sequence[Score],
    screens: Sequence[ScreenResult],
    alerts: Sequence[Alert],
) -> None:
    """Store a completed run and all its outputs in one transaction."""
    run_id = record.run_id
    conn.execute("BEGIN TRANSACTION")
    try:
        insert_rows(conn, "runs", [_run_row(record)])
        insert_rows(
            conn,
            "metric_values",
            [
                {
                    "run_id": run_id,
                    "metric_id": row.metric_id,
                    "issuer_id": row.issuer_id,
                    "level": row.level.value,
                    "entity_id": row.entity_id,
                    "status": row.result.status.value,
                    "value": row.result.value,
                    "detail": row.result.detail,
                    "inputs": json.dumps(dict(row.result.inputs), ensure_ascii=False),
                }
                for row in metrics.rows
            ],
        )
        insert_rows(
            conn,
            "scores",
            [
                {
                    "run_id": run_id,
                    "issuer_id": score.issuer_id,
                    "score_type": score.score_type.value,
                    "value": score.value,
                    "coverage": score.coverage,
                    "factors_with_data": score.factors_with_data,
                    "displayed": score.displayed,
                    "reason": score.reason,
                }
                for score in scores
            ],
        )
        insert_rows(
            conn,
            "score_components",
            [_component_row(run_id, s, c) for s in scores for c in s.components],
        )
        insert_rows(
            conn,
            "screen_results",
            [
                {
                    "run_id": run_id,
                    "issuer_id": result.issuer_id,
                    "screen_id": result.screen_id,
                    "outcome": result.outcome.value,
                    "conditions": json.dumps(
                        [
                            {
                                "description": c.description,
                                "outcome": c.outcome.value,
                                "detail": c.detail,
                            }
                            for c in result.conditions
                        ],
                        ensure_ascii=False,
                    ),
                }
                for result in screens
            ],
        )
        insert_rows(
            conn,
            "alerts",
            [
                {
                    "run_id": run_id,
                    "alert_id": number,
                    "rule": alert.rule.value,
                    "issuer_id": alert.issuer_id,
                    "entity_id": alert.entity_id,
                    "message": alert.message,
                    "details": json.dumps(dict(alert.details), ensure_ascii=False),
                }
                for number, alert in enumerate(alerts, start=1)
            ],
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def save_failed_run(conn: duckdb.DuckDBPyConnection, record: RunRecord) -> None:
    """Record a run that did not finish (it has no outputs)."""
    insert_rows(conn, "runs", [_run_row(record)])


def list_runs(conn: duckdb.DuckDBPyConnection) -> list[RunRecord]:
    """Every run, oldest first."""
    rows = conn.execute(f"SELECT {_RUN_COLUMNS} FROM runs ORDER BY started_at, run_id").fetchall()
    return [_record_from_row(row) for row in rows]


def get_run(conn: duckdb.DuckDBPyConnection, run_id: str) -> RunRecord | None:
    row = conn.execute(f"SELECT {_RUN_COLUMNS} FROM runs WHERE run_id = ?", [run_id]).fetchone()
    return None if row is None else _record_from_row(row)


def latest_completed_run(
    conn: duckdb.DuckDBPyConnection, *, before_as_of: date | None = None
) -> RunRecord | None:
    """Most recent completed run (by analysis date, then start time), optionally before a date."""
    row = conn.execute(
        f"SELECT {_RUN_COLUMNS} FROM runs WHERE status = 'completed'"
        " AND (?::DATE IS NULL OR as_of_date < ?)"
        " ORDER BY as_of_date DESC, started_at DESC LIMIT 1",
        [before_as_of, before_as_of],
    ).fetchone()
    return None if row is None else _record_from_row(row)


def load_scores(conn: duckdb.DuckDBPyConnection, run_id: str) -> list[Score]:
    """Scores of a run with their components, as they were stored."""
    components: dict[tuple[str, str], list[ScoreComponent]] = {}
    for row in conn.execute(
        "SELECT issuer_id, score_type, metric_id, weight, status, value, detail,"
        " reference_group, peer_count, percentile, contribution"
        " FROM score_components WHERE run_id = ? ORDER BY rowid",
        [run_id],
    ).fetchall():
        issuer_id, score_type, metric_id, weight, status, value, detail, group, peers = row[:9]
        percentile, contribution = row[9:]
        components.setdefault((issuer_id, score_type), []).append(
            ScoreComponent(
                metric_id=metric_id,
                weight=weight,
                status=Status(status),
                value=value,
                detail=detail,
                reference_group=ReferenceGroup(group) if group else None,
                peer_count=peers,
                percentile=percentile,
                contribution=contribution,
            )
        )
    scores = []
    for row in conn.execute(
        "SELECT issuer_id, score_type, value, coverage, factors_with_data, displayed, reason"
        " FROM scores WHERE run_id = ? ORDER BY score_type, issuer_id",
        [run_id],
    ).fetchall():
        issuer_id, score_type, value, coverage, factors, displayed, reason = row
        scores.append(
            Score(
                issuer_id=issuer_id,
                score_type=ScoreType(score_type),
                value=value,
                coverage=coverage,
                factors_with_data=factors,
                displayed=displayed,
                reason=reason,
                components=tuple(components.get((issuer_id, score_type), [])),
            )
        )
    return scores


def previous_scores(conn: duckdb.DuckDBPyConnection, as_of: date) -> PreviousScores | None:
    """Scores of the latest completed run with an analysis date before ``as_of``."""
    record = latest_completed_run(conn, before_as_of=as_of)
    if record is None:
        return None
    scores = {(s.issuer_id, s.score_type): s for s in load_scores(conn, record.run_id)}
    return PreviousScores(record.run_id, record.as_of_date, record.config_hash, scores)


def load_metric_table(conn: duckdb.DuckDBPyConnection, run_id: str) -> MetricTable:
    """Metric results of a run, with their inputs, as they were stored."""
    rows = conn.execute(
        "SELECT metric_id, issuer_id, level, entity_id, status, value, detail, inputs"
        " FROM metric_values WHERE run_id = ? ORDER BY rowid",
        [run_id],
    ).fetchall()
    return MetricTable(
        MetricRow(
            metric_id,
            issuer_id,
            EntityLevel(level),
            entity_id,
            MetricResult(Status(status), value, detail, json.loads(inputs)),
        )
        for metric_id, issuer_id, level, entity_id, status, value, detail, inputs in rows
    )


def load_screen_results(conn: duckdb.DuckDBPyConnection, run_id: str) -> list[ScreenResult]:
    rows = conn.execute(
        "SELECT issuer_id, screen_id, outcome, conditions FROM screen_results"
        " WHERE run_id = ? ORDER BY rowid",
        [run_id],
    ).fetchall()
    return [
        ScreenResult(
            issuer_id,
            screen_id,
            ScreenOutcome(outcome),
            tuple(
                ConditionResult(c["description"], ScreenOutcome(c["outcome"]), c["detail"])
                for c in json.loads(conditions)
            ),
        )
        for issuer_id, screen_id, outcome, conditions in rows
    ]


def load_alerts(conn: duckdb.DuckDBPyConnection, run_id: str) -> list[Alert]:
    rows = conn.execute(
        "SELECT rule, issuer_id, entity_id, message, details FROM alerts"
        " WHERE run_id = ? ORDER BY alert_id",
        [run_id],
    ).fetchall()
    return [
        Alert(AlertRule(rule), issuer_id, entity_id, message, json.loads(details))
        for rule, issuer_id, entity_id, message, details in rows
    ]
