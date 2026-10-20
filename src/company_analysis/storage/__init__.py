"""Local storage in DuckDB: schema migrations, append-only loads and point-in-time reads.

Run records and outputs live in ``company_analysis.storage.runs``.
"""

from company_analysis.storage.database import connect, migrate, open_database
from company_analysis.storage.repository import (
    LoadBatch,
    LoadResult,
    bundle_hash,
    latest_price_date,
    list_load_batches,
    read_bundle,
    save_bundle,
)

__all__ = [
    "LoadBatch",
    "LoadResult",
    "bundle_hash",
    "connect",
    "latest_price_date",
    "list_load_batches",
    "migrate",
    "open_database",
    "read_bundle",
    "save_bundle",
]
