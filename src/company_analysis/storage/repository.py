"""Input data access: append-only loads and point-in-time reads.

A read "at ``as_of`` with ``cutoff``" sees, for each key, the latest version that had been
published by ``as_of`` (no look-ahead) and loaded no later than ``cutoff`` (reproducible runs).
"""

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import duckdb

from company_analysis.clock import utc_now
from company_analysis.models import DataBundle
from company_analysis.models.base import DomainModel
from company_analysis.storage.database import insert_rows

# Bundle collection (= table name) -> natural key, without load_id.
_KEYS: dict[str, tuple[str, ...]] = {
    "issuers": ("issuer_id",),
    "equities": ("isin",),
    "bonds": ("isin",),
    "financial_facts": ("issuer_id", "fiscal_period", "period_end", "item"),
    "equity_prices": ("isin", "price_date"),
    "bond_quotes": ("isin", "quote_date"),
    "ratings": ("isin", "agency", "rating_date"),
    "fx_rates": ("currency", "rate_date"),
}


@dataclass(frozen=True)
class LoadBatch:
    load_id: str
    loaded_at: datetime
    provider: str
    content_hash: str
    row_counts: dict[str, int]


@dataclass(frozen=True)
class LoadResult:
    batch: LoadBatch
    created: bool  # False when the same content had already been loaded


def bundle_hash(bundle: DataBundle) -> str:
    """Fingerprint of a bundle's content, used to make loads idempotent."""
    return hashlib.sha256(bundle.model_dump_json().encode("utf-8")).hexdigest()


def _insert(
    conn: duckdb.DuckDBPyConnection, table: str, load_id: str, records: Sequence[DomainModel]
) -> None:
    insert_rows(conn, table, [{"load_id": load_id, **record.model_dump()} for record in records])


def _batch_from_row(row: tuple[Any, ...]) -> LoadBatch:
    load_id, loaded_at, provider, content_hash, row_counts = row
    return LoadBatch(load_id, loaded_at, provider, content_hash, json.loads(row_counts))


def save_bundle(
    conn: duckdb.DuckDBPyConnection,
    bundle: DataBundle,
    provider: str,
    *,
    loaded_at: datetime | None = None,
) -> LoadResult:
    """Store a bundle as a new load batch, in one transaction. Never updates existing rows.

    Loading exactly the same content again does not create a new batch.
    """
    content_hash = bundle_hash(bundle)
    existing = conn.execute(
        "SELECT load_id, loaded_at, provider, content_hash, row_counts FROM load_batches"
        " WHERE provider = ? AND content_hash = ?",
        [provider, content_hash],
    ).fetchone()
    if existing is not None:
        return LoadResult(_batch_from_row(existing), created=False)

    timestamp = loaded_at or utc_now()
    batch = LoadBatch(
        load_id=f"L{timestamp:%Y%m%dT%H%M%S}-{content_hash[:8]}",
        loaded_at=timestamp,
        provider=provider,
        content_hash=content_hash,
        row_counts=bundle.row_counts(),
    )
    conn.execute("BEGIN TRANSACTION")
    try:
        conn.execute(
            "INSERT INTO load_batches VALUES (?, ?, ?, ?, ?)",
            [batch.load_id, batch.loaded_at, provider, content_hash, json.dumps(batch.row_counts)],
        )
        for table in _KEYS:
            _insert(conn, table, batch.load_id, getattr(bundle, table))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return LoadResult(batch, created=True)


def list_load_batches(
    conn: duckdb.DuckDBPyConnection, *, until: datetime | None = None
) -> list[LoadBatch]:
    """Load batches in loading order, optionally only those loaded up to ``until``."""
    rows = conn.execute(
        "SELECT load_id, loaded_at, provider, content_hash, row_counts FROM load_batches"
        " WHERE ?::TIMESTAMP IS NULL OR loaded_at <= ? ORDER BY loaded_at, load_id",
        [until, until],
    ).fetchall()
    return [_batch_from_row(row) for row in rows]


def _records(
    conn: duckdb.DuckDBPyConnection, sql: str, params: Sequence[object]
) -> list[dict[str, Any]]:
    cursor = conn.execute(sql, list(params))
    columns = [column[0] for column in cursor.description or []]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _latest_versions(
    conn: duckdb.DuckDBPyConnection,
    table: str,
    *,
    cutoff: datetime,
    condition: str = "",
    params: Sequence[object] = (),
    newest_first: str = "",
) -> list[dict[str, Any]]:
    """Latest version of each key among the batches loaded up to ``cutoff``."""
    key = ", ".join(f"t.{column}" for column in _KEYS[table])
    sql = f"""
        SELECT t.* EXCLUDE (load_id)
        FROM {table} AS t JOIN load_batches AS b ON b.load_id = t.load_id
        WHERE b.loaded_at <= ? {condition}
        QUALIFY row_number() OVER (
            PARTITION BY {key} ORDER BY {newest_first} b.loaded_at DESC, b.load_id DESC
        ) = 1
        ORDER BY {key}
    """
    return _records(conn, sql, [cutoff, *params])


def read_bundle(
    conn: duckdb.DuckDBPyConnection,
    *,
    as_of: date,
    cutoff: datetime,
    history_start: date | None = None,
) -> DataBundle:
    """Data as known at ``as_of``, using only batches loaded up to ``cutoff``.

    - Financial facts: published by ``as_of``; a later publication (restatement) replaces an
      earlier one, and a later load replaces an earlier load of the same publication.
    - Prices, quotes and exchange rates: observed by ``as_of`` (and since ``history_start``).
    - Bonds: only those outstanding at ``as_of``; ratings: full history up to ``as_of``.
    """
    since = history_start or date.min
    bonds = [
        bond
        for bond in _latest_versions(conn, "bonds", cutoff=cutoff)
        if bond["issue_date"] <= as_of < bond["maturity_date"]
    ]
    outstanding = {bond["isin"] for bond in bonds}
    collections = {
        "issuers": _latest_versions(conn, "issuers", cutoff=cutoff),
        "equities": _latest_versions(conn, "equities", cutoff=cutoff),
        "bonds": bonds,
        "financial_facts": _latest_versions(
            conn,
            "financial_facts",
            cutoff=cutoff,
            condition="AND t.published_at <= ? AND t.period_end >= ?",
            params=(as_of, since),
            newest_first="t.published_at DESC,",
        ),
        "equity_prices": _latest_versions(
            conn,
            "equity_prices",
            cutoff=cutoff,
            condition="AND t.price_date BETWEEN ? AND ?",
            params=(since, as_of),
        ),
        "bond_quotes": [
            quote
            for quote in _latest_versions(
                conn,
                "bond_quotes",
                cutoff=cutoff,
                condition="AND t.quote_date BETWEEN ? AND ?",
                params=(since, as_of),
            )
            if quote["isin"] in outstanding
        ],
        "ratings": [
            rating
            for rating in _latest_versions(
                conn, "ratings", cutoff=cutoff, condition="AND t.rating_date <= ?", params=(as_of,)
            )
            if rating["isin"] in outstanding
        ],
        "fx_rates": _latest_versions(
            conn,
            "fx_rates",
            cutoff=cutoff,
            condition="AND t.rate_date BETWEEN ? AND ?",
            params=(since, as_of),
        ),
    }
    return DataBundle.model_validate(collections)


def latest_price_date(conn: duckdb.DuckDBPyConnection) -> date | None:
    """Most recent share price date loaded: the default analysis date."""
    row = conn.execute("SELECT max(price_date) FROM equity_prices").fetchone()
    return None if row is None else row[0]
