"""Stateless date and time helpers."""

from datetime import UTC, date, datetime


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """Read a stored timestamp as UTC.

    `UTCDateTime` is `DateTime(timezone=True)`, and **SQLite ignores the
    timezone**: what PostgreSQL hands back aware, the unit suite hands back
    naive. So anything that compares a stored timestamp to `utc_now()` raises
    "can't subtract offset-naive and offset-aware datetimes" in the tests and
    works in production, or the reverse -- neither of which anybody wants to
    discover from a stack trace.

    Everything this repo stores is UTC, so a naive value is a UTC value that
    lost its label on the way out of the database. Say so once, here, rather
    than at every call site.

    Args:
        value: A timestamp read from the database.

    Returns:
        The same instant, timezone-aware.

    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def parse_iso_date(value: str) -> date:
    """Parse a strict ISO-8601 calendar date."""
    return date.fromisoformat(value)


def financial_year_label(on: date, *, start_month: int = 4) -> str:
    """Return the ``YYYY-YYYY`` financial year that a date falls in.

    Document numbers embed this label, and the transactional modules disagreed
    on it three ways: ``2025-2026``, ``2025-26`` and a plain calendar ``2026``.
    Documents from the same period therefore carried incomparable numbers. Four
    of them also hardcoded an April start instead of reading the firm's own
    financial year.

    Args:
        on: The document date.
        start_month: First month of the financial year, 1-12. Callers pass the
            month from the firm's ``financial_year_start``.

    Returns:
        The label, for example ``"2025-2026"``.

    Raises:
        ValueError: If ``start_month`` is not a calendar month.

    """
    if not 1 <= start_month <= 12:
        raise ValueError("start_month must be between 1 and 12.")
    start_year = on.year if on.month >= start_month else on.year - 1
    return f"{start_year}-{start_year + 1}"
