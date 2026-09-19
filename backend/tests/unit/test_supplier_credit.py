"""Supplier credit: what a purchase return off the goods receipt leaves.

D-FIN-19, driven on TEST01 on 2026-09-19 (fixture ``po-invoiced``, suffix
t0919trod): PR-2026-2027-000009 sent back 2 against the receipt of 4 --
completed, 236.00 debited to payables -- and nothing tracked it per supplier.
PI-2026-2027-000012 still showed 708.00 outstanding, was paid in full
(PY-2026-2027-000002), and the supplier was then deleted (204) with the
236.00 in payables belonging to nobody.

A return raised from the bill's own lines already comes off that bill
(D-BUY-6). One raised from the receipt is now a supplier credit: listed for
the vendor, set against a bill on request (which then owes that much less,
with no journal -- the return and the bill already posted), and counted by the
vendor delete guard.
"""

from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.exceptions import ValidationError
from app.purchase_invoice.models import PurchaseInvoice
from app.purchase_return.models import PurchaseReturn, PurchaseReturnLine
from app.settlements.api.router import (
    apply_vendor_supplier_credit,
    vendor_supplier_credits,
)
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
    withdraw_credit_applications,
)
from app.vendors.models import Vendor
from app.vendors.services.vendor_service import VendorService
from tests.unit.test_settlements import WHEN, _Books, _session_factory


def _return(
    books: _Books,
    number: str,
    *,
    total: str,
    status: str = "COMPLETED",
    source_type: str = "GOODS_RECEIPT",
    bill: PurchaseInvoice | None = None,
) -> PurchaseReturn:
    """Record a return of one line, as rows: nothing here is about its posting."""
    row = PurchaseReturn(
        firm_id=books.firm.id,
        vendor_id=books.vendor.id,
        branch_id=books.branch_id,
        warehouse_id=uuid4(),
        return_number=number,
        return_date=WHEN,
        status=status,
        grand_total=Decimal(total),
        created_by=books.actor_id,
        updated_by=books.actor_id,
    )
    books.session.add(row)
    books.session.flush()
    books.session.add(
        PurchaseReturnLine(
            purchase_return_id=row.id,
            firm_id=books.firm.id,
            line_number=1,
            source_document_type=source_type,
            source_document_id=bill.id if bill is not None else uuid4(),
            source_document_number=(
                bill.invoice_number if bill is not None else "GRN-1"
            ),
            source_document_line_id=uuid4(),
            source_document_line_number=1,
            product_id=uuid4(),
            received_quantity=Decimal("4"),
            already_returned_quantity=Decimal("0"),
            current_return_quantity=Decimal("2"),
            net_amount=Decimal(total),
            created_by=books.actor_id,
            updated_by=books.actor_id,
        )
    )
    books.session.commit()
    return row


def _owed(books: _Books) -> dict[str, Decimal]:
    """Return what each of the vendor's bills still owes, by number."""
    return {
        record.invoice_number: record.outstanding_amount
        for record in PaymentService(books.session).outstanding_invoices(
            firm_id=books.firm.id, party_id=books.vendor.id
        )
    }


def _scope(books: _Books) -> object:
    """Build the resolved firm scope a request carries."""
    from types import SimpleNamespace

    return SimpleNamespace(firm_id=books.firm.id, actor_id=books.actor_id)


def test_a_return_off_the_receipt_is_a_credit_the_next_bill_can_take() -> None:
    """The credit is listed, set against a bill, and the bill owes less."""
    books = _Books(_session_factory()())
    bill = books.purchase_invoice("PI-1", "708.00")
    credit = _return(books, "PR-1", total="236.00")
    # None of these gives credit: not posted, cancelled, or already off a bill.
    _return(books, "PR-DRAFT", total="50.00", status="APPROVED")
    _return(books, "PR-GONE", total="60.00", status="CANCELLED")
    _return(books, "PR-BILL", total="118.00", source_type="PURCHASE_INVOICE", bill=bill)

    listed = vendor_supplier_credits(
        vendor_id=books.vendor.id,
        scope=_scope(books),  # type: ignore[arg-type]
        db=books.session,
    ).data
    assert listed is not None
    assert [(row.return_number, row.available_amount) for row in listed] == [
        ("PR-1", Decimal("236.00"))
    ]
    # The bill-sourced return already came off the bill (D-BUY-6); the credit
    # has not, until somebody sets it there.
    assert _owed(books) == {"PI-1": Decimal("590.00")}

    applied = apply_vendor_supplier_credit(
        return_id=credit.id,
        payload=SupplierCreditApplyRequest(invoice_id=bill.id, amount=Decimal("200")),
        scope=_scope(books),  # type: ignore[arg-type]
        db=books.session,
    ).data
    assert applied is not None
    assert applied.available_amount == Decimal("36.00")
    assert applied.applied_to == ["PI-1"]
    assert _owed(books) == {"PI-1": Decimal("390.00")}

    # And a payment is held to what is left.
    with pytest.raises(ValidationError, match="390.00 outstanding"):
        PaymentService(books.session).create(
            SettlementCreate(
                party_id=books.vendor.id,
                settlement_date=WHEN,
                amount=Decimal("590.00"),
                method=SettlementMethodEnum.BANK,
                allocations=[
                    SettlementAllocationWrite(invoice_id=bill.id, amount=Decimal("590"))
                ],
            ),
            firm_id=books.firm.id,
            actor_id=books.actor_id,
        )


def test_a_credit_is_set_off_only_within_what_both_sides_hold() -> None:
    """More than the credit, more than the bill, another supplier's bill: no."""
    books = _Books(_session_factory()())
    bill = books.purchase_invoice("PI-1", "100.00")
    credit = _return(books, "PR-1", total="236.00")
    other = Vendor(
        firm_id=books.firm.id,
        code="V2",
        name="Vendor Two",
        display_name="Vendor Two",
        created_by=books.actor_id,
        updated_by=books.actor_id,
    )
    books.session.add(other)
    books.session.commit()
    elsewhere = PurchaseInvoice(
        firm_id=books.firm.id,
        vendor_id=other.id,
        branch_id=books.branch_id,
        invoice_number="PI-OTHER",
        invoice_date=WHEN,
        supplier_invoice_number="S-OTHER",
        supplier_invoice_date=WHEN,
        status="APPROVED",
        grand_total=Decimal("500.00"),
        created_by=books.actor_id,
        updated_by=books.actor_id,
    )
    books.session.add(elsewhere)
    books.session.commit()

    def _apply(invoice_id: object, amount: str) -> None:
        apply_supplier_credit(
            books.session,
            firm_id=books.firm.id,
            purchase_return_id=credit.id,
            invoice_id=invoice_id,  # type: ignore[arg-type]
            amount=Decimal(amount),
            actor_id=books.actor_id,
        )

    with pytest.raises(ValidationError, match="PI-1 owes only 100.00"):
        _apply(bill.id, "150")
    with pytest.raises(ValidationError, match="not this supplier's"):
        _apply(elsewhere.id, "10")
    _apply(bill.id, "100")
    books.session.commit()
    second = books.purchase_invoice("PI-2", "500.00")
    with pytest.raises(ValidationError, match="only 136.00 of credit left"):
        _apply(second.id, "200")
    draft = _return(books, "PR-DRAFT", total="50.00", status="APPROVED")
    with pytest.raises(ValidationError, match="leaves no credit"):
        apply_supplier_credit(
            books.session,
            firm_id=books.firm.id,
            purchase_return_id=draft.id,
            invoice_id=second.id,
            amount=Decimal("10"),
            actor_id=books.actor_id,
        )


def test_a_supplier_holding_a_credit_cannot_be_deleted() -> None:
    """The vendor delete guard counts the credit, as it counts an advance."""
    books = _Books(_session_factory()())
    credit = _return(books, "PR-1", total="236.00")

    with pytest.raises(ValidationError, match="236.00 of supplier credit.*PR-1"):
        VendorService(books.session).delete(
            books.vendor.id, firm_scope=books.firm.id, actor_id=books.actor_id
        )

    # Set against a bill it clears in full, the account is square.
    bill = books.purchase_invoice("PI-1", "236.00")
    apply_supplier_credit(
        books.session,
        firm_id=books.firm.id,
        purchase_return_id=credit.id,
        invoice_id=bill.id,
        amount=Decimal("236.00"),
        actor_id=books.actor_id,
    )
    books.session.commit()
    VendorService(books.session).delete(
        books.vendor.id, firm_scope=books.firm.id, actor_id=books.actor_id
    )


def test_withdrawing_an_application_frees_the_credit_and_the_bill() -> None:
    """Cancelling either side withdraws what was set between them."""
    books = _Books(_session_factory()())
    bill = books.purchase_invoice("PI-1", "708.00")
    credit = _return(books, "PR-1", total="236.00")
    apply_supplier_credit(
        books.session,
        firm_id=books.firm.id,
        purchase_return_id=credit.id,
        invoice_id=bill.id,
        amount=Decimal("236.00"),
        actor_id=books.actor_id,
    )
    books.session.commit()
    assert _owed(books) == {"PI-1": Decimal("472.00")}

    assert (
        withdraw_credit_applications(
            books.session,
            firm_id=books.firm.id,
            actor_id=books.actor_id,
            purchase_invoice_id=bill.id,
        )
        == 1
    )
    books.session.commit()
    assert _owed(books) == {"PI-1": Decimal("708.00")}
    found = supplier_credits(books.session, firm_id=books.firm.id)
    assert found[0].available_amount == Decimal("236.00")
    assert books.session.query(SupplierCreditApplication).count() == 1


def test_cancelling_the_bill_frees_the_credit_set_against_it() -> None:
    """The bill's payable is gone, so the credit is the supplier's again."""
    from app.purchase_invoice.services import PurchaseInvoiceService

    books = _Books(_session_factory()())
    bill = books.purchase_invoice("PI-1", "708.00")
    credit = _return(books, "PR-1", total="236.00")
    apply_supplier_credit(
        books.session,
        firm_id=books.firm.id,
        purchase_return_id=credit.id,
        invoice_id=bill.id,
        amount=Decimal("236.00"),
        actor_id=books.actor_id,
    )
    books.session.commit()

    bills = PurchaseInvoiceService(books.session)
    # The bill was built as a row, so its document type is set up here, as
    # raising a bill through the service would have done.
    bills._ensure_document_setup(firm_id=books.firm.id, actor_id=books.actor_id)
    bills.cancel_invoice(
        bill.id, firm_scope=books.firm.id, actor_id=books.actor_id, reason="wrong"
    )

    found = supplier_credits(books.session, firm_id=books.firm.id)
    assert found[0].available_amount == Decimal("236.00")
    assert found[0].applied_to == []
