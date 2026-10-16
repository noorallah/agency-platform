"""Refuse a reporting period that ends before it starts, for every route at once.

About seventy dated reports take ``from_date`` and ``to_date`` as query
parameters, and a pair that ran backwards (``from_date=2026-12-31&
to_date=2025-04-01``) answered 200 with an empty list -- a report of nothing,
indistinguishable from a period in which nothing happened (D-RPT-23). Sales
analysis already refused it in its service. Rather than repeat that check in
every handler, `refuse_backwards_period` is registered once as an application
dependency in ``app/main.py``, so it runs for every route and the next report
added is covered without anybody remembering to.

It reads the raw query string, not the handler's parameters, so it only acts
when both values are present and both are ISO dates; anything it cannot read
is left to the route's own validation, which answers its usual 422.
"""

from datetime import date

from fastapi import Request

from app.core.exceptions.base import ValidationError

#: The message sales analysis has always given for the same refusal.
BACKWARDS_PERIOD_MESSAGE = "The period must not run backwards."


def _as_date(raw: str | None) -> date | None:
    """Read one query value as an ISO date, or ``None`` when it is not one."""
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def refuse_backwards_period(request: Request) -> None:
    """Refuse a request whose ``from_date`` falls after its ``to_date``.

    A single day (the two equal) and an open-ended period (either left out)
    pass.

    Raises:
        ValidationError: A 422 in the standard envelope, naming both fields.

    """
    start = _as_date(request.query_params.get("from_date"))
    end = _as_date(request.query_params.get("to_date"))
    if start is not None and end is not None and start > end:
        raise ValidationError(
            BACKWARDS_PERIOD_MESSAGE,
            details=[
                {
                    "field": "from_date",
                    "message": f"{start.isoformat()} is after the to_date "
                    f"{end.isoformat()}.",
                }
            ],
        )
