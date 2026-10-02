"""Supplier credit set against an opening bill (BUY-17, decision A52).

A firm moving from other software brings its suppliers' unpaid bills over as
opening bills, and the first purchase return after cutover is often against
goods on one of them. Until BUY-17 the credit could be set only against a
purchase bill: the opening bill was refused by name and stayed owed in full
while the supplier's credit sat unused. Now the application names the opening
bill, nothing posts, and every reader of the opening bill's balance -- Record
Payment, the opening bill list, the vendor delete guard -- sees it owe less.
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.exceptions import ValidationError
from app.finance.models import JournalEntry
from app.settlements.api.router import apply_vendor_supplier_credit
from app.settlements.models import SupplierCreditApplication
from app.settlements.schemas import (
    SettlementAllocationWrite,
    SettlementCreate,
    SettlementMethodEnum,
    SupplierCreditApplyRequest,
)
from app.settlements.services import PaymentService
from app.settlements.services.supplier_credits import (
    apply_supplier_credit,
    supplier_credits,
)
from app.vendors.models import VendorOpeningBill
from app.vendors.schemas.opening_bill import VendorOpeningBillWrite
from app.vendors.services.opening_bill_service import VendorOpeningBillService
from tests.unit.test_settlements import WHEN, _Books, _session_factory
from tests.unit.test_supplier_credit import _owed, _return, _scope

# Fixtures here type their document numbers; see conftest (D-CFG-2).
pytestmark = pytest.mark.typed_document_numbers


def _opening_bill(books: _Books, amount: str) -> VendorOpeningBill:
    """Record one bill the firm owed the vendor at cutover."""
    return VendorOpeningBillService(books.session).create(
        books.vendor.id,
        VendorOpeningBillWrite(
            reference_number="OLD-77",
            bill_date=date(2026, 2, 10),
            posting_date=date(2026, 4, 1),
            amount=Decimal(amount),
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )


def _journals(books: _Books) -> int:
    """Count the journals in the firm's books."""
    return int(books.session.scalar(select(func.count()).select_from(JournalEntry)))


def test_a_credit_is_set_against_an_opening_bill_which_then_owes_less() -> None:
    """The opening bill owes less everywhere it is read; nothing posts."""
    books = _Books(_session_factory()())
    bill = _opening_bill(books, "800.00")
    credit = _return(books, "PR-1", total="236.00")
    assert _owed(books) == {"OLD-77 (opening)": Decimal("800.00")}
    journals = _journals(books)

    applied = apply_vendor_supplier_credit(
        return_id=credit.id,
        payload=SupplierCreditApplyRequest(invoice_id=bill.id, amount=Decimal("200")),
        scope=_scope(books),  # type: ignore[arg-type]
        db=books.session,
    ).data

    assert applied is not None
    assert applied.available_amount == Decimal("36.00")
    assert applied.applied_to == ["OLD-77 (opening)"]
    assert _owed(books) == {"OLD-77 (opening)": Decimal("600.00")}
    assert _journals(books) == journals
    row = books.session.scalars(select(SupplierCreditApplication)).one()
    assert row.vendor_opening_bill_id == bill.id
    assert row.purchase_invoice_id is None
    # The opening bill list says the same as Record Payment.
    listed = VendorOpeningBillService(books.session).response_for(
        bill, firm_id=books.firm.id
    )
    assert (listed.paid_amount, listed.outstanding_amount) == (
        Decimal("200.00"),
        Decimal("600.00"),
    )
    # And a payment is held to what is left.
    with pytest.raises(ValidationError, match="600.00 outstanding"):
        PaymentService(books.session).create(
            SettlementCreate(
                party_id=books.vendor.id,
                settlement_date=WHEN,
                amount=Decimal("800.00"),
                method=SettlementMethodEnum.BANK,
                allocations=[
                    SettlementAllocationWrite(invoice_id=bill.id, amount=Decimal("800"))
                ],
            ),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )


def test_an_opening_bill_takes_no_more_credit_than_it_owes() -> None:
    """Past what the opening bill owes is refused; up to it settles it."""
    books = _Books(_session_factory()())
    bill = _opening_bill(books, "100.00")
    credit = _return(books, "PR-1", total="236.00")

    with pytest.raises(ValidationError, match="owes only 100.00"):
        apply_supplier_credit(
            books.session,
            firm_id=books.firm.id,
            source_id=credit.id,
            invoice_id=bill.id,
            amount=Decimal("150"),
            actor_id=books.actor_id,
        )
    apply_supplier_credit(
        books.session,
        firm_id=books.firm.id,
        source_id=credit.id,
        invoice_id=bill.id,
        amount=Decimal("100"),
        actor_id=books.actor_id,
    )
    books.session.commit()

    assert _owed(books) == {}
    [left] = supplier_credits(books.session, firm_id=books.firm.id)
    assert left.available_amount == Decimal("136.00")


def test_cancelling_an_opening_bill_frees_the_credit_set_against_it() -> None:
    """Credit does not hold the cancel up, as money paid does; it comes back."""
    books = _Books(_session_factory()())
    bill = _opening_bill(books, "800.00")
    credit = _return(books, "PR-1", total="236.00")
    apply_supplier_credit(
        books.session,
        firm_id=books.firm.id,
        source_id=credit.id,
        invoice_id=bill.id,
        amount=Decimal("236"),
        actor_id=books.actor_id,
    )
    books.session.commit()

    VendorOpeningBillService(books.session).cancel(
        bill.id, reason="entered twice", firm_id=books.firm.id, actor_id=uuid4()
    )

    assert bill.status == "CANCELLED"
    assert _owed(books) == {}
    [freed] = supplier_credits(books.session, firm_id=books.firm.id)
    assert freed.available_amount == Decimal("236.00")
    assert freed.applied_to == []


def test_an_opening_bill_with_money_paid_is_still_refused_a_cancel() -> None:
    """Only the credit is exempt: a payment applied still holds the bill."""
    books = _Books(_session_factory()())
    bill = _opening_bill(books, "800.00")
    credit = _return(books, "PR-1", total="236.00")
    apply_supplier_credit(
        books.session,
        firm_id=books.firm.id,
        source_id=credit.id,
        invoice_id=bill.id,
        amount=Decimal("236"),
        actor_id=books.actor_id,
    )
    PaymentService(books.session).create(
        SettlementCreate(
            party_id=books.vendor.id,
            settlement_date=WHEN,
            amount=Decimal("100.00"),
            method=SettlementMethodEnum.BANK,
            allocations=[
                SettlementAllocationWrite(invoice_id=bill.id, amount=Decimal("100"))
            ],
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )
    books.session.commit()

    with pytest.raises(ValidationError, match="100.00 has been paid"):
        VendorOpeningBillService(books.session).cancel(
            bill.id, reason="entered twice", firm_id=books.firm.id, actor_id=uuid4()
        )
