"""The GST time limits that run out on 30 November after a year (backlog GST-1).

Two acts on a year's supplies stop being possible on the same date:

* tax on a **credit note** for a supply can no longer be reduced once 30
  November after the end of the supply's financial year has passed (CGST
  s.34(2), as amended by the Finance Act 2022);
* **input credit** on a bill can no longer be claimed after that date
  (s.16(4)).

Both end "on 30 November or on the date the annual return is filed, whichever
is earlier". Nothing here records when a firm filed its annual return, so the
30 November date is the one named; a firm that filed earlier is told the
outer limit, which is a warning rather than a refusal for exactly that reason.

The GST year is April to March whatever a firm's own accounting year, so the
date is computed from the statute, never from ``financial_year_start``.
"""

from __future__ import annotations

from datetime import date


def gst_year_of(on: date) -> int:
    """Return the calendar year in which the GST year holding ``on`` starts.

    Args:
        on: A document date.

    Returns:
        ``2025`` for any date from 1 April 2025 to 31 March 2026.

    """
    return on.year if on.month >= 4 else on.year - 1


def gst_year_label(on: date) -> str:
    """Return the ``2025-26`` label of the GST year holding ``on``."""
    start = gst_year_of(on)
    return f"{start}-{(start + 1) % 100:02d}"


def november_limit(supply_date: date) -> date:
    """Return 30 November after the end of the GST year holding ``supply_date``.

    Args:
        supply_date: The date of the supply (the invoice or bill date).

    Returns:
        The last day a credit note may reduce its tax, or its credit be
        claimed.

    """
    return date(gst_year_of(supply_date) + 1, 11, 30)


def credit_note_time_limit_warning(
    supply_date: date | None, note_date: date
) -> str | None:
    """Say why a credit note dated ``note_date`` can no longer reduce tax.

    Args:
        supply_date: The date of the invoice the note credits, if known.
        note_date: The credit note's (or the return's) own date.

    Returns:
        The warning, or ``None`` while the note is within the limit.

    """
    if supply_date is None:
        return None
    limit = november_limit(supply_date)
    if note_date <= limit:
        return None
    return (
        f"The supply was made in {gst_year_label(supply_date)}, so the tax on "
        f"a credit note for it could be reduced only until "
        f"{limit:%d %b %Y} (CGST s.34(2)), or the date the annual return was "
        "filed if earlier. Approved as it stands, it still takes the tax off "
        "the books and out of GSTR-1 -- check with your CA before approving."
    )
