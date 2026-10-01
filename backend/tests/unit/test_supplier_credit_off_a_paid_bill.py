"""D-BUY-20: a return off a bill that was already paid leaves a supplier credit.

A return raised from a bill's own lines comes off that bill (D-BUY-6). When the
bill was already paid, or paid all but less than the return, there is nothing
left on it to come off: `outstanding_invoices` dropped the bill, and
`supplier_credits` counted only receipt-sourced returns, so the payables debit
the return posted belonged to no credit -- it could not be set against the next
bill or paid back.

What the bill cannot absorb is now the return's supplier credit, newest return
first. If that credit is used and the bill later owes more again (its payment
reversed), the part used goes back onto the bill, so the payable list and the
ledger still agree.
"""

from decimal import Decimal

from app.settlements.schemas import (
    SettlementAllocationWrite,
    SettlementCreate,
    SettlementMethodEnum,
)
from app.settlements.services import PaymentService
from app.settlements.services.supplier_credits import (
    apply_supplier_credit,
    supplier_credits,
)
from app.vendors.services.vendor_service import VendorService
from tests.unit.test_settlements import WHEN, _Books, _session_factory
from tests.unit.test_supplier_credit import _owed, _return


def _pay(books: _Books, bill_id: object, amount: str) -> object:
    """Pay part or all of one bill."""
    return PaymentService(books.session).create(
        SettlementCreate(
            party_id=books.vendor.id,
            settlement_date=WHEN,
            amount=Decimal(amount),
            method=SettlementMethodEnum.BANK,
            allocations=[
                SettlementAllocationWrite(
                    invoice_id=bill_id,  # type: ignore[arg-type]
                    amount=Decimal(amount),
                )
            ],
        ),
        firm_id=books.firm.id,
        actor_id=books.actor_id,
    )


def _available(books: _Books) -> dict[str, Decimal]:
    """Return each credit's available amount, by return number."""
    return {
        credit.return_number: credit.available_amount
        for credit in supplier_credits(books.session, firm_id=books.firm.id)
    }


def test_a_return_off_a_paid_bill_is_a_credit() -> None:
    """Paid in full: the whole return is the supplier's to give back."""
    books = _Books(_session_factory()())
    bill = books.purchase_invoice("PI-1", "708.00")
    _pay(books, bill.id, "708.00")
    credit = _return(
        books, "PR-1", total="236.00", source_type="PURCHASE_INVOICE", bill=bill
    )

    assert _owed(books) == {}
    assert _available(books) == {"PR-1": Decimal("236.00")}

    # It can be set against the next bill, like any other credit.
    second = books.purchase_invoice("PI-2", "500.00")
    apply_supplier_credit(
        books.session,
        firm_id=books.firm.id,
        purchase_return_id=credit.id,
        invoice_id=second.id,
        amount=Decimal("236.00"),
        actor_id=books.actor_id,
    )
    books.session.commit()
    assert _owed(books) == {"PI-2": Decimal("264.00")}
    assert _available(books) == {"PR-1": Decimal("0.00")}


def test_only_what_the_bill_cannot_absorb_is_credit_newest_return_first() -> None:
    """Paid 600 of 708: a return of 100 still fits, the next one spills over."""
    books = _Books(_session_factory()())
    bill = books.purchase_invoice("PI-1", "708.00")
    _pay(books, bill.id, "600.00")
    _return(books, "PR-1", total="100.00", source_type="PURCHASE_INVOICE", bill=bill)
    assert _owed(books) == {"PI-1": Decimal("8.00")}
    assert _available(books) == {}

    _return(books, "PR-2", total="236.00", source_type="PURCHASE_INVOICE", bill=bill)
    assert _owed(books) == {}
    # 600 + 100 + 236 = 936 against 708: 228 over, all of it the later return's.
    assert _available(books) == {"PR-2": Decimal("228.00")}

    # And the supplier cannot be deleted while it stands.
    import pytest

    from app.core.exceptions import ValidationError

    with pytest.raises(ValidationError, match="228.00 of supplier credit"):
        VendorService(books.session).delete(
            books.vendor.id, firm_scope=books.firm.id, actor_id=books.actor_id
        )


def test_a_used_credit_goes_back_on_the_bill_when_its_payment_is_reversed() -> None:
    """The payable list keeps agreeing with the ledger after the payment goes.

    Ledger: PI-1 708 + PI-2 500, less the return's 236 = 972 owed. Applying
    posts nothing, so the bills between them must still owe 972.
    """
    books = _Books(_session_factory()())
    bill = books.purchase_invoice("PI-1", "708.00")
    payment = _pay(books, bill.id, "708.00")
    credit = _return(
        books, "PR-1", total="236.00", source_type="PURCHASE_INVOICE", bill=bill
    )
    second = books.purchase_invoice("PI-2", "500.00")
    apply_supplier_credit(
        books.session,
        firm_id=books.firm.id,
        purchase_return_id=credit.id,
        invoice_id=second.id,
        amount=Decimal("236.00"),
        actor_id=books.actor_id,
    )
    books.session.commit()

    PaymentService(books.session).reverse(
        payment.id,  # type: ignore[attr-defined]
        firm_id=books.firm.id,
        actor_id=books.actor_id,
        reason="bounced",
    )

    owed = _owed(books)
    assert owed == {"PI-1": Decimal("708.00"), "PI-2": Decimal("264.00")}
    assert sum(owed.values()) == Decimal("972.00")
    assert _available(books) == {}
