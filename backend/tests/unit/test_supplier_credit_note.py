"""The supplier's own credit note, with no goods back (BACKLOG 68 row 10).

Recorded as the debit note it is from our side, with the supplier's number and
date on it (OWNER_DECISIONS A31): a rate difference or a discount after
billing. These hold it to what the row asks -- against a bill, the payable and
the input credit come down, GSTR-3B reports the reversal, the supplier
statement names it -- and to its reversal putting all of that back.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.common.firm_metadata import firm_today
from app.core.exceptions import ValidationError
from app.debit_note.models import DebitNote
from app.debit_note.schemas import DebitNoteReasonEnum, DebitNoteUpdate
from app.debit_note.services import DebitNoteService
from app.gst_returns.services.gstr_service import GstReturnService
from app.vendors.services.statement_service import SupplierStatementService
from tests.unit.test_debit_note import WHEN, _Books

pytestmark = pytest.mark.typed_document_numbers

APRIL = (date(2026, 4, 1), date(2026, 4, 30))


def _credit_note(
    books: _Books,
    *,
    number: str | None = "SCN-7",
    when: date | None = WHEN,
    taxable: str = "100",
) -> DebitNote:
    """Record the supplier's credit note for a discount after billing."""
    data = books.payload(taxable, reason=DebitNoteReasonEnum.DISCOUNT).model_copy(
        update={
            "supplier_credit_note_number": number,
            "supplier_credit_note_date": when,
        }
    )
    row = DebitNoteService(books.session).create_note(
        data, firm_id=books.firm.id, actor_id=books.actor_id
    )
    books.session.commit()
    return row


def _approve(books: _Books, row: DebitNote) -> None:
    """Approve a recorded note."""
    DebitNoteService(books.session).approve_note(
        row.id, firm_scope=books.firm.id, actor_id=books.actor_id
    )
    books.session.commit()


def _itc_reversed(books: _Books) -> dict[str, object]:
    """Return GSTR-3B table 4B for April."""
    itc = GstReturnService(books.session)._input_tax_credit(
        firm_scope=books.firm.id, from_date=APRIL[0], to_date=APRIL[1]
    )
    reversed_ = itc["itc_reversed"]
    assert isinstance(reversed_, dict)
    return reversed_


def test_it_reduces_the_bill_the_input_credit_and_3b() -> None:
    """100 + 18 off the bill; 9 + 9 reversed in 4B; the response carries it."""
    books = _Books()
    row = _credit_note(books)
    _approve(books, row)

    assert books.owed() == Decimal("1062.00")
    reversed_ = _itc_reversed(books)
    assert (reversed_["central_tax"], reversed_["state_tax"]) == (9.0, 9.0)
    response = DebitNoteService(books.session).note_response(row)
    assert response.reason == DebitNoteReasonEnum.DISCOUNT
    assert response.supplier_credit_note_number == "SCN-7"
    assert response.supplier_credit_note_date == WHEN
    assert response.tax_amount == Decimal("18.0000")


def test_the_supplier_statement_names_it() -> None:
    """A debit on the supplier's account, remarks naming their credit note."""
    books = _Books()
    _approve(books, _credit_note(books))

    statement = SupplierStatementService(books.session).statement(
        books.vendor.id, firm_scope=books.firm.id, from_date=APRIL[0], to_date=APRIL[1]
    )
    [line] = [line for line in statement.lines if line.transaction_type == "DEBIT_NOTE"]
    assert line.debit == Decimal("118.00")
    assert "supplier's credit note SCN-7" in (line.remarks or "")


def test_cancelling_it_puts_the_payable_and_the_credit_back() -> None:
    """The reversal restores what the bill owes and nets 3B to nothing."""
    books = _Books()
    row = _credit_note(books)
    _approve(books, row)
    DebitNoteService(books.session).cancel_note(
        row.id,
        reason="credit note withdrawn by the supplier",
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()

    assert books.owed() == Decimal("1180.00")
    reversed_ = _itc_reversed(books)
    assert (reversed_["central_tax"], reversed_["state_tax"]) == (0.0, 0.0)
    # The mirror is dated the day it was cancelled, so read up to today.
    statement = SupplierStatementService(books.session).statement(
        books.vendor.id,
        firm_scope=books.firm.id,
        from_date=APRIL[0],
        to_date=max(firm_today(books.session, books.firm.id), APRIL[1]),
    )
    kinds = [line.transaction_type for line in statement.lines]
    assert kinds == ["DEBIT_NOTE", "DEBIT_NOTE_REVERSAL"]
    assert statement.closing_balance == Decimal("0.00")
    # A cancelled note frees its number to be recorded again.
    _credit_note(books)


def test_it_is_recorded_whole_not_early_and_once() -> None:
    """Number without date, a date before the bill, a second copy: refused."""
    books = _Books()
    with pytest.raises(ValidationError, match="both its number and its date"):
        _credit_note(books, when=None)
    books.session.rollback()
    with pytest.raises(ValidationError, match="before the bill it credits"):
        _credit_note(books, when=WHEN - timedelta(days=1))
    books.session.rollback()
    first = _credit_note(books, taxable="50")
    with pytest.raises(
        ValidationError, match=f"recorded on debit note {first.debit_note_number}"
    ):
        _credit_note(books, number="scn-7", taxable="50")


def test_an_edit_can_record_or_clear_it_and_the_list_filters_on_it() -> None:
    """Our own claim gains the supplier's number later; the filter follows."""
    books = _Books()
    ours = books.note("40")
    theirs = _credit_note(books, taxable="40")
    service = DebitNoteService(books.session)

    def listed(flag: bool | None, search: str | None = None) -> set[str]:
        """Return the note numbers the list gives for a filter."""
        rows, _ = service.list_notes(
            firm_scope=books.firm.id,
            page=1,
            page_size=20,
            supplier_credit_note=flag,
            search=search,
        )
        return {row.debit_note_number for row in rows}

    assert listed(True) == {theirs.debit_note_number}
    assert listed(False) == {ours.debit_note_number}
    assert listed(None, "SCN-7") == {theirs.debit_note_number}

    service.update_note(
        ours.id,
        DebitNoteUpdate.model_validate(
            {
                "supplier_credit_note_number": "SCN-8",
                "supplier_credit_note_date": WHEN,
            }
        ),
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
    )
    service.update_note(
        theirs.id,
        DebitNoteUpdate.model_validate(
            {"supplier_credit_note_number": None, "supplier_credit_note_date": None}
        ),
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    assert listed(True) == {ours.debit_note_number}
    with pytest.raises(ValidationError, match="both its number and its date"):
        service.update_note(
            ours.id,
            DebitNoteUpdate.model_validate({"supplier_credit_note_date": None}),
            firm_scope=books.firm.id,
            actor_id=books.actor_id,
        )
