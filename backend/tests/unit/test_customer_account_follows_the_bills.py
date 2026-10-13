"""The customer's account goes on agreeing with the bills (row G4).

Four things that left it a little off them, each found by reading the account
beside the bills over HTTP:

* returns rounded one by one posted 117.99 or 118.01 against a bill of 118.00
  (D-FIN-28);
* a line typed at a rate including GST could not be returned at all: 500 at
  84.7458 are 42,372.90 where the bill charged 42,372.88 (row F1's left-over);
* a return of goods no bill had charged stated a value and nothing beside it
  said that it credited nothing (D-SELL-90);
* a debit note on a paid bill with a return left the customer owing the
  charge on no bill and holding as much from no source (D-FIN-29).
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.core.exceptions import ValidationError
from app.customer_debit_note.schemas import (
    CustomerDebitNoteCreate,
    CustomerDebitNoteLineWrite,
)
from app.customer_debit_note.services import CustomerDebitNoteService
from app.customers.models import Customer, CustomerReceivableTransaction
from app.finance.models import GLPosting
from app.inventory.schemas import InventoryAdjustmentCreate
from app.inventory.services import InventoryService
from app.purchase_return.models import PurchaseReturn
from app.purchase_return.services import PurchaseReturnService
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine
from app.sales_invoice.services import SalesInvoiceService
from app.sales_return.models import SalesReturn
from app.sales_return.schemas import SalesReturnCreate
from app.sales_return.services import SalesReturnService
from app.settlements.services.customer_credits import customer_credits
from tests.unit.test_customer_credit_applications import _balances, _receipt
from tests.unit.test_lines_in_another_unit import (
    _bill,
    _brought_back,
    _gst_18,
    _owed,
    _shipped,
    _Shop,
)
from tests.unit.test_purchase_return_before_billing import _received, _send_back
from tests.unit.test_sales_invoice_rate_includes_tax import _bill_of_an_order
from tests.unit.test_sales_return_module import (
    _Dispatch,
    _on_the_line_of,
    _returned,
    _session_factory,
)

D = Decimal


def _account(shop: _Shop, bill: SalesInvoice) -> tuple[Decimal, Decimal]:
    """Return what the bill's customer owes and holds."""
    shop.session.expire_all()
    customer = shop.session.get(Customer, bill.customer_id)
    assert customer is not None
    return (
        D(str(customer.current_outstanding)).quantize(D("0.01")),
        D(str(customer.unapplied_advance_balance)).quantize(D("0.01")),
    )


def _credited_by_journals(shop: _Shop) -> list[Decimal]:
    """Return what each sales return's journal credited, oldest first."""
    # The credit journal each return names; its cost journal is another.
    entries = shop.session.execute(
        select(SalesReturn.journal_entry_id)
        .where(SalesReturn.journal_entry_id.is_not(None))
        .order_by(SalesReturn.created_at, SalesReturn.return_number)
    ).all()
    return [
        D(
            str(
                shop.session.scalar(
                    select(func.max(GLPosting.credit_amount)).where(
                        GLPosting.journal_entry_id == entry_id
                    )
                )
            )
        ).quantize(D("0.01"))
        for (entry_id,) in entries
    ]


@pytest.mark.parametrize(
    ("parts", "posted"),
    [
        (("4", "4", "4"), [D("39.33"), D("39.34"), D("39.33")]),
        (("5", "5", "2"), [D("49.17"), D("49.16"), D("19.67")]),
    ],
)
def test_part_returns_of_a_bill_add_up_to_the_bill(
    parts: tuple[str, ...], posted: list[Decimal]
) -> None:
    """A box at 100.00 plus 18% back in parts credits 118.00, to the paisa.

    Each return rounded on its own posted 39.33 three times, 117.99, and the
    customer owed 0.01 on no bill; as 5, 5 and 2 it posted 118.01 and they
    held 0.01 from no source (D-FIN-28). Each now takes what the bill's own
    reading moves by.
    """
    shop = _Shop()
    _gst_18(shop)
    bill, billed = _bill(shop, _shipped(shop, "1", unit_price="100"), "1")
    source = ("SALES_INVOICE", bill.id, billed.id)
    assert _account(shop, bill) == (D("118.00"), D("0.00"))

    for part in parts:
        _brought_back(shop, source, part, return_uom_id=shop.piece)

    assert _credited_by_journals(shop) == posted
    assert _owed(shop, bill) == D("0.00")
    assert _account(shop, bill) == (D("0.00"), D("0.00"))
    # The account's own rows say the same as the journals.
    rows = shop.session.scalars(
        select(CustomerReceivableTransaction.amount)
        .where(CustomerReceivableTransaction.reference_type == "SALES_RETURN")
        .order_by(
            CustomerReceivableTransaction.created_at,
            CustomerReceivableTransaction.reference_number,
        )
    ).all()
    assert [D(str(amount)).quantize(D("0.01")) for amount in rows] == posted


def test_one_return_of_a_whole_bill_posts_its_own_figure() -> None:
    """Nothing to make up: a bill returned at once is credited as it reads."""
    shop = _Shop()
    _gst_18(shop)
    bill, billed = _bill(shop, _shipped(shop, "1", unit_price="100"), "1")

    _brought_back(shop, ("SALES_INVOICE", bill.id, billed.id), "1")

    assert _credited_by_journals(shop) == [D("118.00")]
    assert _account(shop, bill) == (D("0.00"), D("0.00"))


def _approved_inclusive_bill(quantity: str) -> tuple[object, SalesInvoice, UUID]:
    """Bill and approve an order typed at 100.00 including 18% GST."""
    setup, invoice = _bill_of_an_order(
        inclusive=True, quantity=D(quantity), rate=D("100")
    )
    # The fixture stocks a hundred; five hundred are about to leave.
    InventoryService(setup.session).create_adjustment(
        InventoryAdjustmentCreate(
            branch_id=setup.branch.id,
            warehouse_id=setup.warehouse.id,
            product_id=setup.product.id,
            quantity=D("1000"),
            reference_number="ADJ-G4",
            reference_type="ADJUSTMENT",
            transaction_date=date(2026, 8, 1),
        ),
        firm_scope=setup.firm.id,
        actor_id=invoice.created_by,
    )
    invoice = SalesInvoiceService(setup.session).approve_invoice(
        invoice.id, firm_scope=setup.firm.id, actor_id=invoice.created_by
    )
    setup.session.commit()
    line_id = setup.session.scalar(
        select(SalesInvoiceLine.id).where(
            SalesInvoiceLine.sales_invoice_id == invoice.id
        )
    )
    assert line_id is not None
    return setup, invoice, line_id


def _back_off_the_bill(
    setup: object, invoice: SalesInvoice, line_id: UUID, quantity: str, **line: object
) -> SalesReturn:
    """Return some of the bill's line, through to completion."""
    service = SalesReturnService(setup.session)  # type: ignore[attr-defined]
    firm_id = setup.firm.id  # type: ignore[attr-defined]
    row = service.create_return(
        SalesReturnCreate.model_validate(
            {
                "warehouse_id": setup.warehouse.id,  # type: ignore[attr-defined]
                "return_date": date(2026, 8, 5),
                "lines": [
                    {
                        "source_document_type": "SALES_INVOICE",
                        "source_document_id": invoice.id,
                        "source_document_line_id": line_id,
                        "line_number": 1,
                        "current_return_quantity": quantity,
                    }
                    | line
                ],
            }
        ),
        firm_id=firm_id,
        actor_id=invoice.created_by,
    )
    service.approve_return(row.id, firm_scope=firm_id, actor_id=invoice.created_by)
    return service.complete_return(
        row.id, firm_scope=firm_id, actor_id=invoice.created_by
    )


def test_a_line_typed_including_gst_is_returned_for_what_it_was_billed() -> None:
    """500 at 100.00 including GST back in full credits 50,000.00.

    The rate before tax is kept to four places, and 500 at 84.7458 are
    42,372.90 where the bill charged 42,372.88: the return was refused as
    crediting more than was billed, with nothing typed on it.
    """
    setup, invoice, line_id = _approved_inclusive_bill("500")
    assert D(str(invoice.grand_total)) == D("50000.0000")

    row = _back_off_the_bill(setup, invoice, line_id, "500")

    assert D(str(row.grand_total)) == D("50000.0000")
    assert D(str(row.subtotal)) == D(str(invoice.subtotal))
    assert D(str(row.tax_total)) == D(str(invoice.tax_total))
    setup.session.expire_all()  # type: ignore[attr-defined]
    customer = setup.session.get(Customer, invoice.customer_id)  # type: ignore[attr-defined]
    assert D(str(customer.current_outstanding)) == D("0")


def test_an_inclusive_line_returned_in_parts_adds_up_to_its_bill() -> None:
    """200, 200 and 100 of the 500 credit 20,000.00, 20,000.00 and 10,000.00."""
    setup, invoice, line_id = _approved_inclusive_bill("500")

    rows = [
        _back_off_the_bill(setup, invoice, line_id, part)
        for part in ("200", "200", "100")
    ]

    assert [D(str(row.grand_total)).quantize(D("0.01")) for row in rows] == [
        D("20000.00"),
        D("20000.00"),
        D("10000.00"),
    ]
    setup.session.expire_all()  # type: ignore[attr-defined]
    customer = setup.session.get(Customer, invoice.customer_id)  # type: ignore[attr-defined]
    assert D(str(customer.current_outstanding)) == D("0")
    assert D(str(customer.unapplied_advance_balance)) == D("0")


def test_a_price_typed_above_the_bills_is_still_refused() -> None:
    """Only a line with nothing typed is brought down to its bill."""
    setup, invoice, line_id = _approved_inclusive_bill("500")

    with pytest.raises(ValidationError, match="cannot be credited more"):
        _back_off_the_bill(setup, invoice, line_id, "500", unit_price="84.7458")


def test_a_return_before_billing_says_it_credits_nothing() -> None:
    """Goods back off a note no bill charged: a value, and 0.00 credited."""
    session = _session_factory()()
    setup = _Dispatch(session, billed=D("0"))

    row = _returned(setup, setup.payload(quantity=D("2")))
    seen = SalesReturnService(session).return_response(row)

    assert seen.grand_total > 0
    assert seen.credited_amount == D("0")


def test_a_return_off_a_bill_says_what_it_credits() -> None:
    """Completed it credits its total; before that, nothing yet."""
    session = _session_factory()()
    setup = _Dispatch(session)
    payload = _on_the_line_of(setup, setup.invoice, "1")

    draft = _returned(setup, payload, complete=False)
    service = SalesReturnService(session)
    assert service.return_response(draft).credited_amount == D("0")

    done = service.complete_return(
        draft.id, firm_scope=setup.firm.id, actor_id=setup.actor_id
    )
    seen = service.return_response(done)
    assert seen.credited_amount == seen.grand_total == D("100.0000")


@pytest.mark.typed_document_numbers
def test_a_purchase_return_before_billing_says_it_claims_nothing() -> None:
    """The buying twin: goods back off a receipt no bill has reached."""
    fixture, receipt = _received("RBG4")

    return_id = _send_back(fixture, receipt, "2")
    row = fixture.session.get(PurchaseReturn, return_id)
    assert row is not None
    seen = PurchaseReturnService(fixture.session).return_response(row)

    assert seen.grand_total > 0
    assert seen.claimed_amount == D("0")


def _debit_note(setup: _Dispatch, taxable: str) -> UUID:
    """Raise and approve a debit note on the bill's line."""
    line_id = setup.session.scalar(
        select(SalesInvoiceLine.id).where(
            SalesInvoiceLine.sales_invoice_id == setup.invoice.id
        )
    )
    service = CustomerDebitNoteService(setup.session)
    note = service.create_note(
        CustomerDebitNoteCreate(
            sales_invoice_id=setup.invoice.id,
            debit_note_date=date(2026, 8, 6),
            lines=[
                CustomerDebitNoteLineWrite(
                    sales_invoice_line_id=line_id,
                    line_number=1,
                    taxable_amount=D(taxable),
                )
            ],
        ),
        firm_id=setup.firm.id,
        actor_id=setup.actor_id,
    )
    service.approve_note(note.id, firm_scope=setup.firm.id, actor_id=setup.actor_id)
    setup.session.commit()
    return note.id


def test_a_debit_note_on_a_paid_bill_with_a_return_meets_its_credit() -> None:
    """Paid 200.00, 100.00 back, then 30.00 more charged: 0.00 owed, 70.00 held.

    The bill is still settled 70.00 past its total, so it owes nothing and
    the return gives 70.00 of credit. The account read 30.00 owed and 100.00
    held: the charge owed on no bill, and as much held from no source
    (D-FIN-29).
    """
    session = _session_factory()()
    setup = _Dispatch(session, billed=D("2"))
    _receipt(setup, "200", (setup.invoice.id, "200"))
    _returned(setup, _on_the_line_of(setup, setup.invoice, "1"))
    session.commit()
    assert _balances(setup) == (D("0.00"), D("100.00"))

    _debit_note(setup, "30")

    assert _balances(setup) == (D("0.00"), D("70.00"))
    (credit,) = customer_credits(
        session, firm_id=setup.firm.id, customer_id=setup.customer.id
    )
    assert (credit.credit_amount, credit.held_amount) == (D("70.00"), D("70.00"))


def test_a_debit_note_on_a_bill_with_no_return_moves_only_what_is_owed() -> None:
    """Nothing to settle up: the customer owes the charge, as before."""
    session = _session_factory()()
    setup = _Dispatch(session, billed=D("2"))
    _receipt(setup, "200", (setup.invoice.id, "200"))

    _debit_note(setup, "30")

    assert _balances(setup) == (D("30.00"), D("0.00"))


def test_cancelling_that_debit_note_names_no_more_than_the_note() -> None:
    """The refusal said 100.00 of a note for 30.00 had been met."""
    session = _session_factory()()
    setup = _Dispatch(session, billed=D("2"))
    _receipt(setup, "200", (setup.invoice.id, "200"))
    _returned(setup, _on_the_line_of(setup, setup.invoice, "1"))
    session.commit()
    note_id = _debit_note(setup, "30")

    with pytest.raises(ValidationError, match=r"already met 30\.00 of this debit"):
        CustomerDebitNoteService(session).cancel_note(
            note_id, firm_scope=setup.firm.id, actor_id=setup.actor_id
        )
