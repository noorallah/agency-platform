"""Stateless date and time helpers."""

from datetime import UTC, date, datetime


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(UTC)


def parse_iso_date(value: str) -> date:
    """Parse a strict ISO-8601 calendar date."""
    return date.fromisoformat(value)
