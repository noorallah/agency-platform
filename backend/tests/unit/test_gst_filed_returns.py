"""Filed GSTR-1 figures stay filed; later changes are amendments (GST-6, A130).

April is filed with one invoice, SI-1 at 1000 + 180. Afterwards SI-1 is
corrected to 1200 + 216 and SI-2, dated in April, is raised late. April's
return still reads as filed; May's carries SI-1 in B2BA (declared 1000,
revised 1200) and SI-2 as added, and 3B for May states 1200 more taxable and
216 more tax. Once May is filed, June has nothing left to amend.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from app.gst_returns.models import GstReturnFiling, GstReturnType
from app.gst_returns.services import GstReturnService
from app.gst_returns.services.tax_calendar import TaxCalendarService
from app.sales_invoice.models import SalesInvoiceLine, SalesInvoiceLineTax
from tests.unit.test_gst_returns import _Books, _session_factory

D = Decimal
APRIL = (date(2026, 4, 1), date(2026, 4, 30))
MAY = (date(2026, 5, 1), date(2026, 5, 31))
JUNE = (date(2026, 6, 1), date(2026, 6, 30))


def _gstr1(books: _Books, period: tuple[date, date]) -> dict[str, Any]:
    return GstReturnService(books.session).gstr1(
        firm_scope=books.firm.id, from_date=period[0], to_date=period[1]
    )


def _file(books: _Books, month: str, on: date) -> None:
    TaxCalendarService(books.session).mark_filed(
        books.firm.id,
        return_type=GstReturnType.GSTR1,
        return_period=month,
        filed_on=on,
        actor_id=uuid4(),
    )
    books.session.commit()


def _numbers(data: dict[str, Any]) -> list[str]:
    return [
        invoice["invoice_number"]
        for party in data["b2b"]
        for invoice in party["invoices"]
    ]


def _correct(books: _Books, number: str) -> None:
    """Raise SI-1 from 1000 + 180 to 1200 + 216 after it was filed."""
    line = books.session.scalar(
        select(SalesInvoiceLine).where(
            SalesInvoiceLine.source_document_number == "SO-1",
        )
    )
    assert line is not None
    line.gross_amount = D("1200")
    line.tax_amount = D("216")
    line.net_amount = D("1416")
    for tax in books.session.scalars(
        select(SalesInvoiceLineTax).where(
            SalesInvoiceLineTax.sales_invoice_line_id == line.id
        )
    ):
        tax.amount = D("108")
        tax.base_amount = D("1200")
    books.session.commit()


def test_a_filed_month_stays_filed_and_the_next_carries_the_amendment() -> None:
    books = _Books(_session_factory()())
    books.invoice("SI-1")
    _file(books, "2026-04", date(2026, 5, 10))

    _correct(books, "SI-1")
    books.invoice("SI-2", on=date(2026, 4, 25))

    april = _gstr1(books, APRIL)
    assert april["filed"] is True
    assert _numbers(april) == ["SI-1"]
    assert april["b2b"][0]["invoices"][0]["taxable_value"] == 1000.0

    may = _gstr1(books, MAY)
    assert may["filed"] is False
    (amended,) = may["amendments"]["b2ba"]
    assert amended["original_period"] == "2026-04"
    assert (
        amended["declared"]["taxable_value"],
        amended["revised"]["taxable_value"],
    ) == (1000.0, 1200.0)
    (added,) = may["amendments"]["added"]
    assert added["row"]["invoice_number"] == "SI-2"

    summary = GstReturnService(books.session).gstr3b(
        firm_scope=books.firm.id, from_date=MAY[0], to_date=MAY[1]
    )
    net = summary["amendments_to_earlier_returns"]
    assert net["taxable_value"] == 1200.0  # 200 more on SI-1, 1000 on SI-2
    assert net["central_tax"] + net["state_tax"] == 216.0

    _file(books, "2026-05", date(2026, 6, 10))
    june = _gstr1(books, JUNE)
    assert june["amendments"]["b2ba"] == []
    assert june["amendments"]["added"] == []


def test_withdrawing_a_filing_lets_the_month_move_again() -> None:
    books = _Books(_session_factory()())
    books.invoice("SI-1")
    _file(books, "2026-04", date(2026, 5, 10))
    calendar = TaxCalendarService(books.session)
    row = books.session.scalar(select(GstReturnFiling))
    assert row is not None
    calendar.withdraw(row.id, firm_id=books.firm.id, actor_id=uuid4())
    books.session.commit()
    _correct(books, "SI-1")

    april = _gstr1(books, APRIL)
    assert april["filed"] is False
    assert april["b2b"][0]["invoices"][0]["taxable_value"] == 1200.0


def test_a_month_never_filed_has_nothing_to_amend() -> None:
    books = _Books(_session_factory()())
    books.invoice("SI-1")
    april = _gstr1(books, APRIL)
    assert april["filed"] is False
    assert april["amendments"]["b2ba"] == []
