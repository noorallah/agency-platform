"""Stateless date and time helpers."""

from datetime import UTC, date, datetime, time, timedelta, timezone, tzinfo
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

#: Where a firm keeps its calendar, by the country on the firm: the zone's
#: name, and the fixed offset to fall back on where the machine carries no
#: zone database (a Windows build without ``tzdata``, a slim container). Only
#: countries with one zone and no daylight saving belong here -- the fallback
#: is a constant, so it would be wrong for half the year anywhere else. A
#: country not listed keeps its books on the UTC day, as every firm did
#: before D-CFG-25.
_BUSINESS_ZONES: dict[str, tuple[str, timedelta]] = {
    "IN": ("Asia/Kolkata", timedelta(hours=5, minutes=30)),
}


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


@lru_cache(maxsize=32)
def business_zone(country_code: str | None) -> tzinfo:
    """Return the time zone a firm in ``country_code`` dates its documents in."""
    known = _BUSINESS_ZONES.get((country_code or "").strip().upper())
    if known is None:
        return UTC
    name, offset = known
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return timezone(offset, name)


def business_date(instant: datetime, country_code: str | None) -> date:
    """Return the calendar day an instant falls on for a firm in a country.

    The business date, as opposed to the timestamp. Timestamps are UTC and
    stay UTC; but 01:00 on the 6th in India is 19:30 on the 5th in UTC, and
    a person dating a document "today" means the 6th (D-CFG-25).
    """
    return as_utc(instant).astimezone(business_zone(country_code)).date()


def business_today(country_code: str | None) -> date:
    """Return today's date for a firm in ``country_code``.

    Still `utc_now()` -- the one clock -- read in the firm's own zone. Use it
    wherever "today" is a **business date**: a "not in the future" check on a
    date somebody typed, a report's default as-of day, the date the server
    puts on a document. Firm-owned code reaches it through
    ``firm_today(session, firm_id)`` in ``app/common/firm_metadata.py``, which
    knows the firm's country. An instant -- a token's expiry, an audit
    timestamp, a retention cutoff -- is not a business date and stays on
    `utc_now()`.
    """
    return business_date(utc_now(), country_code)


def business_day_start(day: date, country_code: str | None) -> datetime:
    """Return the UTC instant a firm's calendar ``day`` begins at.

    For drawing a day's boundary round a **timestamp** -- "was it cancelled
    after the 5th", "shifts opened on the 6th". The 6th begins in India at
    18:30 UTC on the 5th, so a boundary drawn at UTC midnight puts everything
    done between 00:00 and 05:30 on the day before: a bill cancelled at 01:00
    on the 6th read as cancelled on the 5th, and an ageing as on the 5th left
    it out although it was still owed that day (D-CFG-25).

    The first instant *after* a day is the start of the next one:
    ``business_day_start(day + timedelta(days=1), country)``; compare a
    timestamp with ``>=`` or ``<`` against it rather than building a
    23:59:59.999999, which leaves a microsecond out.
    """
    return datetime.combine(
        day, time.min, tzinfo=business_zone(country_code)
    ).astimezone(UTC)


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
