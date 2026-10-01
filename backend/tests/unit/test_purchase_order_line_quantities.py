"""One quantity picture per purchase order line (backlog 69 row 5).

An order of 10: 6 arrive, 5 accepted and 1 rejected; 4 are billed; 1 goes
back off the bill. The order now says so on each line -- received, accepted,
rejected, returned, invoiced, still to come, still to bill -- and carries a
billing status beside its lifecycle status rather than in it.
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.finance.services.opening_setup import seed_finance_setup
from app.goods_receipt.models import GoodsReceiptLine
from app.purchase.models import PurchaseOrder, PurchaseOrderLine
from app.purchase.services.purchase_service import PurchaseService
from app.purchase_invoice.models import PurchaseInvoiceLine
from app.purchase_invoice.services import PurchaseInvoiceService
from app.purchase_return.schemas import (
    PurchaseReturnCreate,
    PurchaseReturnLineWrite,
    PurchaseReturnSourceType,
)
from app.purchase_return.services import PurchaseReturnService
from tests.unit import test_purchase_invoice_module as bills

D = Decimal


def _order() -> tuple[Session, PurchaseOrder, PurchaseOrderLine]:
    """Return an approved order of 10 at 100, with the firm's books opened."""
    session = bills._session_factory()()
    firm = bills._firm(session)
    branch = bills._branch(session, firm_id=firm.id)
    warehouse = bills._warehouse(session, firm_id=firm.id, branch_id=branch.id)
    vendor = bills._vendor(session, firm_id=firm.id)
    order = bills._purchase_order(
        session,
        firm_id=firm.id,
        vendor_id=vendor.id,
        branch_id=branch.id,
        warehouse_id=warehouse.id,
    )
    line = session.scalars(
        select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == order.id)
    ).one()
    seed_finance_setup(
        session, firm_id=firm.id, year_starts_on=date(2026, 4, 1), actor_id=uuid4()
    )
    session.commit()
    return session, order, line


def test_an_order_untouched_downstream_owes_everything() -> None:
    """Nothing received: all ten pending, nothing to bill, not invoiced."""
    session, order, _ = _order()
    response = PurchaseService(session).order_response(order)
    [line] = response.lines

    assert line.pending_receipt_quantity == D("10")
    assert line.received_quantity == line.invoiced_quantity == D("0")
    assert line.to_invoice_quantity == D("0")
    assert response.billing_status == "NOT_INVOICED"
    assert response.is_complete is False


def test_each_line_says_what_was_received_rejected_returned_and_billed() -> None:
    """6 in (5 kept, 1 rejected), 4 billed, 1 returned off the bill."""
    session, order, po_line = _order()
    actor_id = uuid4()
    receipt, receipt_line = bills._received(session, po_line)
    receipt_line.current_receipt_quantity = D("6")
    receipt_line.accepted_quantity = D("5")
    receipt_line.rejected_quantity = D("1")
    session.commit()

    invoices = PurchaseInvoiceService(session)
    bill = invoices.create_invoice(
        bills._bill_of(
            receipt, receipt_line, number="SUP-1", quantity="4", on=date(2026, 8, 3)
        ),
        firm_id=order.firm_id,
        actor_id=actor_id,
    )
    invoices.approve_invoice(bill.id, firm_scope=order.firm_id, actor_id=actor_id)
    session.commit()

    halfway = PurchaseService(session).order_response(order)
    [line] = halfway.lines
    assert (line.received_quantity, line.accepted_quantity) == (D("6"), D("5"))
    assert (line.rejected_quantity, line.invoiced_quantity) == (D("1"), D("4"))
    assert line.pending_receipt_quantity == D("4")
    assert line.to_invoice_quantity == D("1")
    assert halfway.billing_status == "PARTIALLY_INVOICED"
    assert halfway.status == order.status, "billing never overwrites the status"

    bill_line = session.scalars(
        select(PurchaseInvoiceLine).where(
            PurchaseInvoiceLine.purchase_invoice_id == bill.id
        )
    ).one()
    returns = PurchaseReturnService(session)
    sent_back = returns.create_return(
        PurchaseReturnCreate(
            return_date=date(2026, 8, 4),
            warehouse_id=order.warehouse_id,
            source_documents=[
                {
                    "source_document_type": PurchaseReturnSourceType.PURCHASE_INVOICE,
                    "source_document_id": bill.id,
                }
            ],
            lines=[
                PurchaseReturnLineWrite(
                    source_document_type=PurchaseReturnSourceType.PURCHASE_INVOICE,
                    source_document_id=bill.id,
                    source_document_line_id=bill_line.id,
                    line_number=1,
                    current_return_quantity=D("1"),
                    warehouse_id=order.warehouse_id,
                )
            ],
        ),
        firm_id=order.firm_id,
        actor_id=actor_id,
    )
    returns.approve_return(sent_back.id, firm_scope=order.firm_id, actor_id=actor_id)
    returns.complete_return(sent_back.id, firm_scope=order.firm_id, actor_id=actor_id)
    session.commit()

    [after] = PurchaseService(session).order_response(order).lines
    assert after.returned_quantity == D("1"), "traced from the bill to the order"
    assert after.to_invoice_quantity == D("0"), "5 kept, 1 back, 4 billed"


def test_received_and_billed_in_full_is_complete() -> None:
    """All ten in, all ten kept and billed: invoiced and complete."""
    session, order, po_line = _order()
    actor_id = uuid4()
    receipt, receipt_line = bills._received(session, po_line)
    invoices = PurchaseInvoiceService(session)
    bill = invoices.create_invoice(
        bills._bill_of(
            receipt, receipt_line, number="SUP-2", quantity="10", on=date(2026, 8, 3)
        ),
        firm_id=order.firm_id,
        actor_id=actor_id,
    )
    session.commit()
    draft = PurchaseService(session).order_response(order)
    assert draft.billing_status == "NOT_INVOICED", "a draft bill has billed nothing"

    invoices.approve_invoice(bill.id, firm_scope=order.firm_id, actor_id=actor_id)
    session.commit()
    done = PurchaseService(session).order_response(order)
    assert done.billing_status == "INVOICED"
    assert done.is_complete is True
    assert session.scalars(select(GoodsReceiptLine)).one().accepted_quantity == D("10")
