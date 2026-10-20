from collections.abc import Iterator
from datetime import date
from pathlib import Path

import duckdb
import pytest

from company_analysis.journal import Decision, JournalError, add_entry, list_entries
from company_analysis.models import DataBundle
from company_analysis.storage import open_database, save_bundle
from tests import factories


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[duckdb.DuckDBPyConnection]:
    with open_database(tmp_path / "journal.duckdb") as connection:
        bundle = DataBundle(
            issuers=(factories.issuer("AAAA"), factories.issuer("BBBB")),
            equities=(factories.equity("AAAA"), factories.equity("BBBB")),
        )
        save_bundle(connection, bundle, "test")
        yield connection


def test_notes_are_listed_newest_first(conn: duckdb.DuckDBPyConnection) -> None:
    add_entry(
        conn, issuer_id="AAAA", text="Tesis inicial", author="Ana", entry_date=date(2026, 1, 10)
    )
    add_entry(
        conn,
        issuer_id="AAAA",
        text="Revisión tras resultados",
        author="Luis",
        decision=Decision.WATCH,
        entry_date=date(2026, 3, 2),
    )
    add_entry(
        conn, issuer_id="BBBB", text="Otra empresa", author="Ana", entry_date=date(2026, 2, 1)
    )
    notes = list_entries(conn, "AAAA")
    assert [n.text for n in notes] == ["Revisión tras resultados", "Tesis inicial"]
    assert notes[0].decision is Decision.WATCH
    assert notes[0].decision.label == "En seguimiento"
    assert len(list_entries(conn)) == 3


@pytest.mark.parametrize(
    ("issuer_id", "text", "author", "message"),
    [
        ("ZZZZ", "Texto", "Ana", "No hay ninguna empresa"),
        ("AAAA", "   ", "Ana", "vacía"),
        ("AAAA", "Texto", " ", "autor"),
    ],
)
def test_invalid_notes_are_rejected(
    conn: duckdb.DuckDBPyConnection, issuer_id: str, text: str, author: str, message: str
) -> None:
    with pytest.raises(JournalError, match=message):
        add_entry(conn, issuer_id=issuer_id, text=text, author=author, entry_date=date(2026, 1, 1))
    assert list_entries(conn) == []
