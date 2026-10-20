"""Analysts' journal: investment theses and notes per company. Entries are never edited."""

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from uuid import uuid4

import duckdb

from company_analysis.clock import utc_now
from company_analysis.storage.database import insert_rows


class Decision(StrEnum):
    """Decision recorded by the analyst (the tool itself never recommends anything)."""

    NONE = "none"
    WATCH = "watch"
    INVEST = "invest"
    HOLD = "hold"
    REDUCE = "reduce"
    DIVEST = "divest"

    @property
    def label(self) -> str:
        return _DECISION_LABELS[self]


_DECISION_LABELS = {
    Decision.NONE: "Sin decisión",
    Decision.WATCH: "En seguimiento",
    Decision.INVEST: "Invertir",
    Decision.HOLD: "Mantener",
    Decision.REDUCE: "Reducir",
    Decision.DIVEST: "Desinvertir",
}


class JournalError(Exception):
    """The note cannot be recorded (unknown company, empty text…)."""


@dataclass(frozen=True)
class JournalEntry:
    entry_id: str
    issuer_id: str
    entry_date: date
    author: str
    text: str
    decision: Decision
    created_at: datetime


def known_issuer(conn: duckdb.DuckDBPyConnection, issuer_id: str) -> bool:
    row = conn.execute("SELECT count(*) FROM issuers WHERE issuer_id = ?", [issuer_id]).fetchone()
    return row is not None and row[0] > 0


def add_entry(
    conn: duckdb.DuckDBPyConnection,
    *,
    issuer_id: str,
    text: str,
    author: str,
    decision: Decision = Decision.NONE,
    entry_date: date,
) -> JournalEntry:
    """Record a new note for a company that exists in the loaded data."""
    if not text.strip():
        raise JournalError("La nota está vacía.")
    if not author.strip():
        raise JournalError("Falta el autor de la nota.")
    if not known_issuer(conn, issuer_id):
        raise JournalError(f"No hay ninguna empresa con el identificador {issuer_id!r}.")
    entry = JournalEntry(
        entry_id=uuid4().hex,
        issuer_id=issuer_id,
        entry_date=entry_date,
        author=author.strip(),
        text=text.strip(),
        decision=decision,
        created_at=utc_now(),
    )
    insert_rows(
        conn,
        "journal_entries",
        [
            {
                "entry_id": entry.entry_id,
                "issuer_id": entry.issuer_id,
                "entry_date": entry.entry_date,
                "author": entry.author,
                "text": entry.text,
                "decision": entry.decision.value,
                "created_at": entry.created_at,
            }
        ],
    )
    return entry


def list_entries(
    conn: duckdb.DuckDBPyConnection, issuer_id: str | None = None
) -> list[JournalEntry]:
    """Notes of one company (or all), most recent first."""
    rows = conn.execute(
        "SELECT entry_id, issuer_id, entry_date, author, text, decision, created_at"
        " FROM journal_entries WHERE ?::VARCHAR IS NULL OR issuer_id = ?"
        " ORDER BY entry_date DESC, created_at DESC",
        [issuer_id, issuer_id],
    ).fetchall()
    return [
        JournalEntry(entry_id, issuer, entry_date, author, text, Decision(decision), created_at)
        for entry_id, issuer, entry_date, author, text, decision, created_at in rows
    ]
