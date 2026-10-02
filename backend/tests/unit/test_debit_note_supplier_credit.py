"""Decision A4: a debit note's excess over what its bill owes is supplier credit.

A debit note against a bill already paid -- or paid all but less than the
claim -- used to be refused ("settled with the supplier, not set against the
bill"). It now behaves as a return off the bill's lines does since D-BUY-20:
what the bill cannot absorb is credit on the supplier's account, to set against
another bill or be paid back, and it goes back on the first bill if that bill
comes to owe more again.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.exceptions import ValidationError
from app.debit_note.models import DebitNote
from app.debit_note.services import DebitNoteService
from app.settlements.models import SettlementMethod, SupplierCreditApplication
from app.settlements.services import PaymentService
from app.settlements.services.supplier_credits import (
    apply_supplier_credit,
    refund_supplier_credit,
    reverse_supplier_refund,
    supplier_credits,
)
from tests.unit.test_debit_note import _Books as _NoteBooks
from tests.unit.test_settlements import WHEN, _Books, _session_factory
from tests.unit.test_supplier_credit import _owed, _return
from tests.unit.test_supplier_credit_off_a_paid_bill import _available, _pay


def _note(
    books: _Books,
    number: str,
    bill: object,
    *,
    taxable: str,
    tax: str = "0",
    on: date = WHEN,
) -> DebitNote:
    """Record an approved debit note, as a row: its posting is not the point."""
    row = DebitNote(
        firm_id=books.firm.id,
        vendor_id=books.vendor.id,
        branch_id=books.branch_id,
        purchase_invoice_id=bill.id,  # type: ignore[attr-defined]
        debit_note_number=number,
        debit_note_date=on,
        status="APPROVED",
        taxable_amount=Decimal(taxable),
        tax_amount=Decimal(tax),
        total_amount=Decimal(taxable) + Decimal(tax),
        created_by=books.actor_id,
        updated_by=books.actor_id,
    )
    books.session.add(row)
    books.session.commit()
    return row


def test_a_debit_note_on_a_paid_bill_is_a_credit() -> None:
    """Paid in full: the whole claim is the supplier's to give back."""
    books = _Books(_session_factory()())
    bill = books.purchase_invoice("PI-1", "708.00")
    _pay(books, bill.id, "708.00")
    note = _note(books, "DN-1", bill, taxable="100", tax="18")

    assert _owed(books) == {}
    [credit] = supplier_credits(books.session, firm_id=books.firm.id)
    assert (credit.source_type, credit.source_id) == ("DEBIT_NOTE", note.id)
    assert credit.purchase_return_id is None
    assert credit.available_amount == Decimal("118.00")

    second = books.purchase_invoice("PI-2", "500.00")
    apply_supplier_credit(
        books.session,
        firm_id=books.firm.id,
        source_id=note.id,
        invoice_id=second.id,
        amount=Decimal("118.00"),
        actor_id=books.actor_id,
    )
    books.session.commit()
    assert _owed(books) == {"PI-2": Decimal("382.00")}
    assert _available(books) == {"DN-1": Decimal("0.00")}
    application = books.session.scalars(select(SupplierCreditApplication)).one()
    assert (application.debit_note_id, application.purchase_return_id) == (
        note.id,
        None,
    )


def test_only_what_the_bill_cannot_absorb_is_credit() -> None:
    """Paid 650 of 708: a claim of 118 takes the last 58 and leaves 60."""
    books = _Books(_session_factory()())
    bill = books.purchase_invoice("PI-1", "708.00")
    _pay(books, bill.id, "650.00")
    _note(books, "DN-1", bill, taxable="100", tax="18")

    assert _owed(books) == {}
    assert _available(books) == {"DN-1": Decimal("60.00")}


def test_returns_and_debit_notes_spill_newest_first_whichever_kind() -> None:
    """The later document is the one the bill could not absorb."""
    books = _Books(_session_factory()())
    bill = books.purchase_invoice("PI-1", "708.00")
    _pay(books, bill.id, "600.00")
    _return(books, "PR-1", total="100.00", source_type="PURCHASE_INVOICE", bill=bill)
    # Dated after the return, so it is the newer of the two.
    _note(books, "DN-1", bill, taxable="50", on=date(2026, 8, 20))

    # 600 + 100 + 50 = 750 against 708: 42 over, all of it the debit note's.
    assert _available(books) == {"DN-1": Decimal("42.00")}


def test_a_used_credit_goes_back_on_the_bill_when_its_payment_is_reversed() -> None:
    """Ledger: 708 + 500 less the note's 118 = 1,090 owed, whatever happens."""
    books = _Books(_session_factory()())
    bill = books.purchase_invoice("PI-1", "708.00")
    payment = _pay(books, bill.id, "708.00")
    note = _note(books, "DN-1", bill, taxable="100", tax="18")
    second = books.purchase_invoice("PI-2", "500.00")
    apply_supplier_credit(
        books.session,
        firm_id=books.firm.id,
        source_id=note.id,
        invoice_id=second.id,
        amount=Decimal("118.00"),
        actor_id=books.actor_id,
    )
    books.session.commit()

    PaymentService(books.session).reverse(
        payment.id,  # type: ignore[attr-defined]
        firm_id=books.firm.id,
        actor_id=books.actor_id,
        reason="bounced",
    )
    books.session.commit()

    owed = _owed(books)
    assert sum(owed.values(), Decimal("0")) == Decimal("1090.00")
    assert owed == {"PI-1": Decimal("708.00"), "PI-2": Decimal("382.00")}


def test_a_debit_note_credit_may_be_paid_back() -> None:
    """No outcome to change first: the supplier sets it off or pays it back."""
    books = _Books(_session_factory()())
    bill = books.purchase_invoice("PI-1", "708.00")
    _pay(books, bill.id, "708.00")
    note = _note(books, "DN-1", bill, taxable="100", tax="18")

    refund = refund_supplier_credit(
        books.session,
        firm_id=books.firm.id,
        source_id=note.id,
        amount=Decimal("100.00"),
        refunded_on=WHEN,
        method=SettlementMethod.BANK,
        actor_id=books.actor_id,
    )
    books.session.commit()

    assert refund.debit_note_id == note.id
    assert refund.purchase_return_id is None
    assert _available(books) == {"DN-1": Decimal("18.00")}

    reverse_supplier_refund(
        books.session,
        firm_id=books.firm.id,
        refund_id=refund.id,
        reason="cheque bounced",
        actor_id=books.actor_id,
    )
    books.session.commit()
    assert _available(books) == {"DN-1": Decimal("118.00")}


# -- Approving and cancelling the real document ----------------------------------


def _paid(books: _NoteBooks) -> None:
    """Pay the debit-note books' bill in full."""
    PaymentService(books.session).create(
        _settlement(books, books.invoice.id, books.owed()),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()


def _settlement(books: _NoteBooks, bill_id: object, amount: Decimal) -> object:
    """Build a bank payment of one bill."""
    from app.settlements.schemas import (
        SettlementAllocationWrite,
        SettlementCreate,
        SettlementMethodEnum,
    )

    return SettlementCreate(
        party_id=books.invoice.vendor_id,
        settlement_date=books.invoice.invoice_date,
        amount=amount,
        method=SettlementMethodEnum.BANK,
        allocations=[
            SettlementAllocationWrite(
                invoice_id=bill_id,  # type: ignore[arg-type]
                amount=amount,
            )
        ],
    )


def test_approving_a_claim_on_a_paid_bill_leaves_a_credit() -> None:
    """Refused until A4; now approved, and the whole claim is credit."""
    books = _NoteBooks()
    _paid(books)
    note = books.note("100")

    DebitNoteService(books.session).approve_note(
        note.id, firm_scope=books.firm.id, actor_id=books.actor_id
    )
    books.session.commit()

    [credit] = supplier_credits(books.session, firm_id=books.firm.id)
    assert credit.debit_note_id == note.id
    assert credit.available_amount == Decimal("118.00")


def test_cancelling_takes_the_credit_back_and_waits_for_a_refund() -> None:
    """A standing refund refuses the cancel; reversed, the cancel goes."""
    books = _NoteBooks()
    _paid(books)
    note = books.approved("100")
    service = DebitNoteService(books.session)
    refund = refund_supplier_credit(
        books.session,
        firm_id=books.firm.id,
        source_id=note.id,
        amount=Decimal("18.00"),
        refunded_on=note.debit_note_date,
        method=SettlementMethod.BANK,
        actor_id=books.actor_id,
    )
    books.session.commit()

    with pytest.raises(ValidationError, match="Reverse that refund"):
        service.cancel_note(
            note.id,
            reason="supplier withdrew",
            firm_scope=books.firm.id,
            actor_id=books.actor_id,
        )
    books.session.rollback()

    reverse_supplier_refund(
        books.session,
        firm_id=books.firm.id,
        refund_id=refund.id,
        reason="entered in error",
        actor_id=books.actor_id,
    )
    service.cancel_note(
        note.id,
        reason="supplier withdrew",
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()
    assert supplier_credits(books.session, firm_id=books.firm.id) == []


def test_cancelling_withdraws_the_credit_set_against_another_bill() -> None:
    """The second bill owes the applied part again once the note goes."""
    from app.purchase_invoice.models import PurchaseInvoice

    books = _NoteBooks()
    _paid(books)
    note = books.approved("100")
    second = PurchaseInvoice(
        firm_id=books.firm.id,
        vendor_id=books.invoice.vendor_id,
        branch_id=books.invoice.branch_id,
        invoice_number="PI-NEXT",
        invoice_date=books.invoice.invoice_date,
        supplier_invoice_number="SUP-NEXT",
        supplier_invoice_date=books.invoice.invoice_date,
        status="APPROVED",
        grand_total=Decimal("500.00"),
    )
    books.session.add(second)
    books.session.commit()
    apply_supplier_credit(
        books.session,
        firm_id=books.firm.id,
        source_id=note.id,
        invoice_id=second.id,
        amount=Decimal("118.00"),
        actor_id=books.actor_id,
    )
    books.session.commit()
    assert books.session.scalars(select(SupplierCreditApplication)).one()

    DebitNoteService(books.session).cancel_note(
        note.id,
        reason="supplier withdrew",
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()

    assert (
        books.session.scalars(
            select(SupplierCreditApplication).where(
                SupplierCreditApplication.is_deleted.is_(False)
            )
        ).all()
        == []
    )
    assert supplier_credits(books.session, firm_id=books.firm.id) == []
