"""Backlog GST-1: a credit note after 30 November warns (CGST s.34(2)).

Tax on a credit note for a year's supplies can be reduced only until 30
November after the year ends. Past it the note is warned -- on the credit
note and on the sales return, which is the firm's credit note for goods --
and still approved: the outer date is all the books know, and whether to
approve is the firm's call with its CA.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from app.credit_note.services import CreditNoteService
from app.sales_return.models import SalesReturn, SalesReturnSource
from app.sales_return.schemas import SalesReturnSourceType, SalesReturnStatus
from app.sales_return.services.sales_return_service import SalesReturnService
from app.tax.services.gst_time_limits import (
    credit_note_time_limit_warning,
    gst_year_label,
    november_limit,
)
from tests.unit.test_credit_note import _Books, _session_factory


@pytest.mark.parametrize(
    ("supply", "limit"),
    [
        (date(2025, 4, 1), date(2026, 11, 30)),
        (date(2026, 3, 31), date(2026, 11, 30)),
        (date(2025, 3, 31), date(2025, 11, 30)),
        (date(2026, 1, 15), date(2026, 11, 30)),
    ],
)
def test_the_limit_is_30_november_after_the_april_to_march_year(
    supply: date, limit: date
) -> None:
    """The GST year is April to March, whatever the firm's own books say."""
    assert november_limit(supply) == limit


def test_the_year_is_named_the_way_returns_name_it() -> None:
    """``2025-26``, as GSTR-1 and the annual return print it."""
    assert gst_year_label(date(2026, 2, 1)) == "2025-26"
    assert gst_year_label(date(2099, 12, 1)) == "2099-00"


def test_a_note_on_the_last_day_is_in_time_and_the_next_day_is_not() -> None:
    """Both ends of the date, since an off-by-one here is a wrong filing."""
    supply = date(2025, 6, 10)

    assert credit_note_time_limit_warning(supply, date(2026, 11, 30)) is None
    late = credit_note_time_limit_warning(supply, date(2026, 12, 1))

    assert late is not None
    assert "2025-26" in late
    assert "30 Nov 2026" in late
    assert "s.34(2)" in late


def test_an_unknown_supply_date_warns_nothing() -> None:
    """No invoice, no year to measure from."""
    assert credit_note_time_limit_warning(None, date(2030, 1, 1)) is None


def test_a_credit_note_for_an_old_year_is_warned_and_still_approved() -> None:
    """A March 2025 invoice credited in April 2026 is fine; in 2024-25 it is not."""
    books = _Books(_session_factory()())
    service = CreditNoteService(books.session)

    in_time = service.note_response(books.note("10"))
    assert in_time.time_limit_warning is None

    books.invoice.invoice_date = date(2024, 6, 1)
    books.session.commit()
    note = books.note("10")
    assert "30 Nov 2025" in (service.note_response(note).time_limit_warning or "")

    service.approve_note(note.id, firm_scope=books.firm.id, actor_id=books.actor_id)
    books.session.commit()
    approved = service.note_response(note)
    assert approved.status.value == "APPROVED"
    assert approved.time_limit_warning is not None


def test_a_credit_note_with_no_tax_or_cancelled_is_not_warned() -> None:
    """Nothing to reduce, so nothing the limit can take away."""
    books = _Books(_session_factory()())
    books.invoice.invoice_date = date(2024, 6, 1)
    books.line.tax_amount = Decimal("0")
    books.session.commit()
    service = CreditNoteService(books.session)

    assert service.note_response(books.note("10")).time_limit_warning is None

    books.line.tax_amount = Decimal("180")
    books.session.commit()
    taxed = books.note("10")
    service.cancel_note(taxed.id, firm_scope=books.firm.id, actor_id=books.actor_id)
    books.session.commit()
    assert service.note_response(taxed).time_limit_warning is None


def _return(
    status: SalesReturnStatus, tax: str, *sources: tuple[str, date]
) -> tuple[SalesReturn, list[SalesReturnSource]]:
    """Build an unsaved return dated 1 December 2026 and its sources."""
    row = SalesReturn(
        status=status.value,
        tax_total=Decimal(tax),
        return_date=date(2026, 12, 1),
    )
    return row, [
        SalesReturnSource(
            source_document_type=kind,
            source_document_id=uuid4(),
            source_document_number="X",
            source_document_date=on,
        )
        for kind, on in sources
    ]


def test_a_return_is_judged_on_the_oldest_invoice_it_credits() -> None:
    """One 2025-26 invoice among 2026-27 ones is enough to be past its date."""
    invoice = SalesReturnSourceType.SALES_INVOICE.value
    row, sources = _return(
        SalesReturnStatus.DRAFT,
        "18",
        (invoice, date(2026, 5, 1)),
        (invoice, date(2026, 2, 1)),
    )

    warning = SalesReturnService._time_limit_warning(row, sources)

    assert warning is not None and "30 Nov 2026" in warning


def test_a_return_from_a_delivery_note_alone_is_not_warned() -> None:
    """Goods not yet invoiced: no tax charged, so none to reduce."""
    row, sources = _return(
        SalesReturnStatus.DRAFT,
        "18",
        (SalesReturnSourceType.DELIVERY_NOTE.value, date(2024, 5, 1)),
    )

    assert SalesReturnService._time_limit_warning(row, sources) is None


def test_a_cancelled_or_tax_free_return_is_not_warned() -> None:
    """Neither reduces any tax."""
    invoice = SalesReturnSourceType.SALES_INVOICE.value
    for status, tax in (
        (SalesReturnStatus.CANCELLED, "18"),
        (SalesReturnStatus.DRAFT, "0"),
    ):
        row, sources = _return(status, tax, (invoice, date(2024, 5, 1)))
        assert SalesReturnService._time_limit_warning(row, sources) is None
