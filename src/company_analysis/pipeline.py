"""One analysis run: read the data known at a date, compute everything and record it.

Every run is recorded, including failed ones, with its analysis date, the data it could see,
the configuration (version, hash and full text) and the version of the code.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import uuid4

import duckdb

from company_analysis.clock import utc_now
from company_analysis.config_loader import LoadedConfig
from company_analysis.metrics import MetricTable, compute_metrics
from company_analysis.models import DataBundle
from company_analysis.normalization import CompanySnapshot, build_snapshots
from company_analysis.provenance import code_version, current_user, git_commit
from company_analysis.scoring import Score, compute_scores
from company_analysis.screening import Alert, ScreenResult, evaluate_alerts, evaluate_screens
from company_analysis.storage import list_load_batches, read_bundle
from company_analysis.storage.runs import (
    RunRecord,
    RunStatus,
    previous_scores,
    save_failed_run,
    save_run,
)

# Enough history for LTM figures, the previous year (growth) and interim periods.
HISTORY = timedelta(days=3 * 366)


class AnalysisError(Exception):
    """The run cannot be done (for example, there is no data loaded)."""


@dataclass(frozen=True)
class RunOutcome:
    record: RunRecord
    bundle: DataBundle
    snapshots: list[CompanySnapshot]
    metrics: MetricTable
    scores: list[Score]
    screens: list[ScreenResult]
    alerts: list[Alert]


def new_run_id(started_at: datetime) -> str:
    """Sortable and unique: ``R20261020T101500-1a2b3c``."""
    return f"R{started_at:%Y%m%dT%H%M%S}-{uuid4().hex[:6]}"


def run_analysis(
    conn: duckdb.DuckDBPyConnection,
    *,
    as_of: date,
    config: LoadedConfig,
    started_at: datetime | None = None,
) -> RunOutcome:
    """Run the whole analysis at ``as_of`` with the data loaded until now, and store it."""
    started = started_at or utc_now()
    run_id = new_run_id(started)
    batches = list_load_batches(conn, until=started)
    methodology = config.config

    def record(status: RunStatus, error: str | None = None) -> RunRecord:
        return RunRecord(
            run_id=run_id,
            started_at=started,
            finished_at=utc_now(),
            as_of_date=as_of,
            data_cutoff=started,
            load_ids=tuple(batch.load_id for batch in batches),
            config_version=config.version,
            config_hash=config.content_hash,
            config_snapshot=config.text,
            code_version=code_version(),
            git_commit=git_commit(),
            triggered_by=current_user(),
            status=status,
            error=error,
        )

    try:
        if not batches:
            raise AnalysisError("No hay datos cargados: ejecuta antes el comando 'cargar'.")
        bundle = read_bundle(conn, as_of=as_of, cutoff=started, history_start=as_of - HISTORY)
        if not bundle.issuers:
            raise AnalysisError("Los datos cargados no contienen emisores.")
        snapshots = build_snapshots(bundle, as_of, methodology.normalization)
        metrics = compute_metrics(snapshots, methodology.metrics)
        scores = compute_scores(snapshots, metrics, methodology.scoring)
        screens = evaluate_screens(snapshots, metrics, methodology.screens)
        alerts = evaluate_alerts(
            snapshots=snapshots,
            ratings=bundle.ratings,
            metrics=metrics,
            scores=scores,
            previous=previous_scores(conn, as_of),
            config=methodology.alerts,
            config_hash=config.content_hash,
            as_of=as_of,
        )
        completed = record(RunStatus.COMPLETED)
        save_run(conn, completed, metrics, scores, screens, alerts)
    except Exception as error:
        save_failed_run(conn, record(RunStatus.FAILED, f"{type(error).__name__}: {error}"))
        raise
    return RunOutcome(completed, bundle, snapshots, metrics, scores, screens, alerts)
