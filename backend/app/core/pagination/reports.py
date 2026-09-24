"""A date range and a page for report endpoints.

Every report used to answer the firm's whole history in one response (D-RPT-18):
a register of two years' invoices, rendered by a grid that is not virtualised.
A dated report now takes ``from_date``/``to_date`` -- inclusive UTC calendar
days on the document's **own** date, never ``created_at`` -- and
``page``/``page_size``, and answers `PaginatedResponse`.

Two ways of paging, and a report uses whichever is correct for it:

* A register read straight from one query pages **in SQL**: `ReportWindow.fetch`
  counts the matches and reads only the page. It returns `ReportRows`, a list
  that remembers the total, so the service's mapping to records can carry it
  through and `ReportWindow.respond` knows not to slice again.
* A report computed in Python -- a group-by, a derived status -- is computed
  over the whole window and the page is sliced from it. Paging its source
  rows would total a page rather than the period.

A snapshot report (stock on hand, balances, what is open today) takes neither.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.orm import QueryableAttribute, Session
from sqlalchemy.sql.elements import ColumnElement

from app.core.constants.core import MAX_PAGE_SIZE
from app.core.pagination.models import PaginationParams
from app.core.responses.models import PaginatedResponse

#: Classic spelling, not ``class ReportRows[RowT]``: Nuitka leaks a class's
#: type parameter into the class body (`app/core/responses/models.py` says why),
#: and `tests/unit/test_no_generic_class_syntax.py` keeps the syntax out.
RowT = TypeVar("RowT")


class ReportRows(list[RowT]):  # noqa: UP046
    """Report rows that know how many matched, when only a page was read.

    A plain list is what every caller that does not page still receives, so a
    service answering this type changes nothing for them.
    """

    def __init__(self, rows: Iterable[RowT] = (), *, total_records: int) -> None:
        """Hold ``rows``, one page of ``total_records`` matches."""
        super().__init__(rows)
        self.total_records = total_records


def mapped_like[RowT](source: Sequence[Any], rows: Iterable[RowT]) -> list[RowT]:
    """Return ``rows``, mapped from ``source``, keeping its total if it was paged.

    A service reads a page of documents and answers a record per document;
    this carries the count of matches from the one to the other.
    """
    if isinstance(source, ReportRows):
        return ReportRows(rows, total_records=source.total_records)
    return list(rows)


@dataclass(frozen=True)
class ReportWindow:
    """The period and the page one report request asked for.

    ``page`` is ``None`` for a caller that wants the whole window, which is
    what a service called from anywhere but a report endpoint receives.
    """

    from_date: date | None = None
    to_date: date | None = None
    page: int | None = None
    page_size: int = MAX_PAGE_SIZE

    def dated(
        self, column: ColumnElement[Any] | QueryableAttribute[Any]
    ) -> list[ColumnElement[bool]]:
        """Return clauses bounding ``column`` to the window, both ends inclusive.

        ``column`` is the document's own `Date` -- the order's `order_date`,
        the invoice's `invoice_date` -- never a `created_at` timestamp: a
        document keyed in on the 2nd for the 1st belongs to the 1st.
        """
        clauses: list[ColumnElement[bool]] = []
        if self.from_date is not None:
            clauses.append(column >= self.from_date)
        if self.to_date is not None:
            clauses.append(column <= self.to_date)
        return clauses

    def fetch(self, session: Session, statement: Select[Any]) -> list[Any]:
        """Read ``statement``'s scalars: one page and a count, or all of them.

        Only for a statement whose rows map one-to-one onto the report's rows;
        a report that groups or filters afterwards must read the whole window.
        """
        if self.page is None:
            return list(session.scalars(statement).all())
        total = session.scalar(
            select(func.count()).select_from(statement.order_by(None).subquery())
        )
        rows = session.scalars(
            statement.offset((self.page - 1) * self.page_size).limit(self.page_size)
        ).all()
        return ReportRows(rows, total_records=int(total or 0))

    def respond[RowT](self, rows: Sequence[RowT]) -> PaginatedResponse[RowT]:
        """Answer ``rows`` as one page, slicing only what was not paged in SQL."""
        params = PaginationParams(page=self.page or 1, page_size=self.page_size)
        if isinstance(rows, ReportRows):
            return PaginatedResponse(
                data=list(rows), pagination=params.metadata(rows.total_records)
            )
        page = list(rows[params.offset : params.offset + params.page_size])
        return PaginatedResponse(data=page, pagination=params.metadata(len(rows)))

    def slice[RowT](self, rows: Sequence[RowT]) -> tuple[list[RowT], int]:
        """Return this window's page of ``rows`` and how many there were."""
        params = PaginationParams(page=self.page or 1, page_size=self.page_size)
        return list(rows[params.offset : params.offset + params.page_size]), len(rows)


#: The default for a service called outside a report endpoint: every date, and
#: every row. A name rather than a call in each signature's default.
WHOLE_HISTORY = ReportWindow()

__all__ = ["WHOLE_HISTORY", "ReportRows", "ReportWindow", "mapped_like"]
