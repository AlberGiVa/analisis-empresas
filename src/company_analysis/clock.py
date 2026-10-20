"""Time helpers. Stored timestamps are naive datetimes in UTC (documented convention)."""

from datetime import UTC, date, datetime


def utc_now() -> datetime:
    """Current time in UTC, without timezone information (as stored in DuckDB)."""
    return datetime.now(UTC).replace(tzinfo=None)


def local_now() -> datetime:
    """Current time in the computer's local timezone (for messages shown to people)."""
    return datetime.now(UTC).astimezone()


def local_today() -> date:
    """Today's date in the computer's local timezone."""
    return local_now().date()
