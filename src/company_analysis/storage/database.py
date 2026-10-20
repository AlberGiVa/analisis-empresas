"""DuckDB connection and schema migrations."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import duckdb

from company_analysis.clock import utc_now

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

# Never download or load extensions on the fly: no network access, reproducible behaviour.
_CONFIG: dict[str, str | bool | int | float | list[str]] = {
    "autoinstall_known_extensions": False,
    "autoload_known_extensions": False,
}


def connect(path: Path, *, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open the database file. DuckDB allows one writer process, or several read-only ones."""
    if not read_only:
        path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path), read_only=read_only, config=_CONFIG)


def migrate(conn: duckdb.DuckDBPyConnection) -> list[int]:
    """Apply pending migrations in order; return the versions applied now."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version INTEGER PRIMARY KEY, name VARCHAR NOT NULL, applied_at TIMESTAMP NOT NULL)"
    )
    applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations").fetchall()}
    newly_applied = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = int(path.name.split("_", 1)[0])
        if version in applied:
            continue
        conn.execute("BEGIN TRANSACTION")
        try:
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT INTO schema_migrations VALUES (?, ?, ?)", [version, path.stem, utc_now()]
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        newly_applied.append(version)
    return newly_applied


@contextmanager
def open_database(path: Path, *, read_only: bool = False) -> Iterator[duckdb.DuckDBPyConnection]:
    """Connection that is migrated on opening (when writable) and always closed afterwards."""
    conn = connect(path, read_only=read_only)
    try:
        if not read_only:
            migrate(conn)
        yield conn
    finally:
        conn.close()
