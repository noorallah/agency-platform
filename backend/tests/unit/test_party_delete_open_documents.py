"""A customer or a vendor with a document still in flight is not deleted.

D-MST-4: the D-FIN-1 guards looked at money and invoices only. A vendor went
with two COMPLETED, unbilled receipts -- goods-received-not-invoiced holding
1,000.00 nobody could bill -- and a customer went under an APPROVED order
holding a reservation. Every sales and purchase service loads the party with
``is_deleted`` false, so the documents could then neither move nor be cleared.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.customers.models import Customer
from app.customers.services import CustomerService
from app.delivery_note.models import DeliveryNote, DeliveryNoteLine
from app.firms.models import Firm
from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
from app.purchase.models import PurchaseOrder, PurchaseOrderLine
from app.purchase_invoice.models import PurchaseInvoice, PurchaseInvoiceLine
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine
from app.sales_order.models import SalesOrder, SalesOrderLine
from app.vendors.models import Vendor
from app.vendors.services import VendorService

TODAY = date(2026, 9, 19)


def _session() -> Session:
    """Open one in-memory database holding the whole schema."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _firm(session: Session, code: str) -> Firm:
    """Add one firm."""
    firm = Firm(
        name=f"{code} Firm",
        code=code,
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(firm)
    session.commit()
    return firm


def _customer(session: Session, firm: Firm, code: str) -> Customer:
    """Add a customer who owes nothing and holds nothing."""
    row = Customer(
        firm_id=firm.id,
        code=code,
        customer_type="BUSINESS",
        name=code,
        display_name=code,
        currency_code="INR",
        status="ACTIVE",
    )
    session.add(row)
    session.commit()
    return row


def _vendor(session: Session, firm: Firm, code: str) -> Vendor:
    """Add a vendor the firm owes nothing."""
    row = Vendor(firm_id=firm.id, code=code, name=code, display_name=code)
    session.add(row)
    session.commit()
    return row


def _order(
    session: Session, firm: Firm, customer_id: UUID, number: str, status: str
) -> SalesOrder:
    """Add a one-line sales order in the given status."""
    order = SalesOrder(
        firm_id=firm.id,
        customer_id=customer_id,
        branch_id=uuid4(),
        warehouse_id=uuid4(),
        order_number=number,
        order_date=TODAY,
        status=status,
    )
    session.add(order)
    session.flush()
    session.add(
        SalesOrderLine(
            sales_order_id=order.id,
            firm_id=firm.id,
            line_number=1,
            product_id=uuid4(),
            quantity=Decimal("1"),
        )
    )
    session.commit()
    return order


def _note(
    session: Session, firm: Firm, customer_id: UUID, number: str, status: str
) -> DeliveryNoteLine:
    """Add a one-line delivery note in the given status and return its line."""
    note = DeliveryNote(
        firm_id=firm.id,
        sales_order_id=uuid4(),
        customer_id=customer_id,
        branch_id=uuid4(),
        warehouse_id=uuid4(),
        delivery_note_number=number,
        delivery_date=TODAY,
        sales_order_reference="SO",
        status=status,
    )
    session.add(note)
    session.flush()
    line = DeliveryNoteLine(
        delivery_note_id=note.id,
        firm_id=firm.id,
        sales_order_line_id=uuid4(),
        line_number=1,
        product_id=uuid4(),
        ordered_quantity=Decimal("1"),
    )
    session.add(line)
    session.commit()
    return line


def _sales_bill(
    session: Session, firm: Firm, customer_id: UUID, line: DeliveryNoteLine
) -> None:
    """Add a CLOSED (fully settled) invoice naming the note line."""
    invoice = SalesInvoice(
        firm_id=firm.id,
        customer_id=customer_id,
        branch_id=uuid4(),
        invoice_number="SI-1",
        invoice_date=TODAY,
        status="CLOSED",
    )
    session.add(invoice)
    session.flush()
    session.add(
        SalesInvoiceLine(
            sales_invoice_id=invoice.id,
            firm_id=firm.id,
            line_number=1,
            source_document_type="DELIVERY_NOTE",
            source_document_id=line.delivery_note_id,
            source_document_number="DN",
            source_document_line_id=line.id,
            source_document_line_number=1,
            product_id=line.product_id,
            delivered_quantity=Decimal("1"),
        )
    )
    session.commit()


def test_a_customer_under_an_open_order_is_refused_by_number() -> None:
    """An approved order holds the customer; a cancelled or closed one does not."""
    session = _session()
    firm = _firm(session, "PD1")
    service = CustomerService(session)
    busy = _customer(session, firm, "PD1-BUSY")
    done = _customer(session, firm, "PD1-DONE")
    _order(session, firm, busy.id, "SO-OPEN", "APPROVED")
    _order(session, firm, done.id, "SO-GONE", "CANCELLED")
    _order(session, firm, done.id, "SO-SHUT", "CLOSED")

    with pytest.raises(ValidationError) as refused:
        service.delete(busy.id, firm_scope=firm.id, actor_id=uuid4())
    assert "PD1-BUSY cannot be deleted" in str(refused.value)
    assert "1 sales order (SO-OPEN)" in str(refused.value)
    session.rollback()
    session.refresh(busy)
    assert busy.is_deleted is False

    service.delete(done.id, firm_scope=firm.id, actor_id=uuid4())
    session.refresh(done)
    assert done.is_deleted is True


def test_goods_shipped_and_not_billed_hold_the_customer() -> None:
    """A dispatched note is open until a live invoice line names it."""
    session = _session()
    firm = _firm(session, "PD2")
    service = CustomerService(session)
    customer = _customer(session, firm, "PD2-C")
    line = _note(session, firm, customer.id, "DN-SHIPPED", "DISPATCHED")

    with pytest.raises(ValidationError, match="1 delivery note \\(DN-SHIPPED\\)"):
        service.delete(customer.id, firm_scope=firm.id, actor_id=uuid4())
    session.rollback()

    _sales_bill(session, firm, customer.id, line)
    service.delete(customer.id, firm_scope=firm.id, actor_id=uuid4())
    session.refresh(customer)
    assert customer.is_deleted is True


def _purchase_order(
    session: Session, firm: Firm, vendor_id: UUID, number: str, status: str
) -> None:
    """Add a one-line purchase order in the given status."""
    order = PurchaseOrder(
        firm_id=firm.id,
        branch_id=uuid4(),
        warehouse_id=uuid4(),
        vendor_id=vendor_id,
        po_number=number,
        purchase_date=TODAY,
        status=status,
    )
    session.add(order)
    session.flush()
    session.add(
        PurchaseOrderLine(
            purchase_order_id=order.id,
            firm_id=firm.id,
            line_number=1,
            product_id=uuid4(),
            ordered_quantity=Decimal("10"),
        )
    )
    session.commit()


def _receipt(
    session: Session, firm: Firm, vendor_id: UUID, number: str
) -> GoodsReceiptLine:
    """Add a COMPLETED one-line goods receipt and return its line."""
    receipt = GoodsReceipt(
        firm_id=firm.id,
        purchase_order_id=uuid4(),
        purchase_order_number="PO",
        vendor_id=vendor_id,
        branch_id=uuid4(),
        warehouse_id=uuid4(),
        grn_number=number,
        receipt_date=TODAY,
        status="COMPLETED",
    )
    session.add(receipt)
    session.flush()
    line = GoodsReceiptLine(
        goods_receipt_id=receipt.id,
        firm_id=firm.id,
        line_number=1,
        purchase_order_line_id=uuid4(),
        purchase_order_line_number=1,
        product_id=uuid4(),
        ordered_quantity=Decimal("10"),
        accepted_quantity=Decimal("10"),
        warehouse_id=receipt.warehouse_id,
    )
    session.add(line)
    session.commit()
    return line


def _purchase_bill(
    session: Session, firm: Firm, vendor_id: UUID, line: GoodsReceiptLine
) -> None:
    """Add a CLOSED (fully paid) supplier invoice naming the receipt line."""
    invoice = PurchaseInvoice(
        firm_id=firm.id,
        vendor_id=vendor_id,
        branch_id=uuid4(),
        invoice_number="PI-1",
        invoice_date=TODAY,
        supplier_invoice_number="SUP-1",
        supplier_invoice_date=TODAY,
        status="CLOSED",
    )
    session.add(invoice)
    session.flush()
    session.add(
        PurchaseInvoiceLine(
            purchase_invoice_id=invoice.id,
            firm_id=firm.id,
            line_number=1,
            source_document_type="GOODS_RECEIPT",
            source_document_id=line.goods_receipt_id,
            source_document_number="GRN",
            source_document_line_id=line.id,
            source_document_line_number=1,
            product_id=line.product_id,
            received_quantity=Decimal("10"),
        )
    )
    session.commit()


def test_a_vendor_over_unbilled_receipts_is_refused_by_number() -> None:
    """Goods taken in and not billed hold the supplier until they are billed."""
    session = _session()
    firm = _firm(session, "PD3")
    service = VendorService(session)
    vendor = _vendor(session, firm, "PD3-V")
    first = _receipt(session, firm, vendor.id, "GRN-A")
    second = _receipt(session, firm, vendor.id, "GRN-B")

    with pytest.raises(ValidationError) as refused:
        service.delete(vendor.id, firm_scope=firm.id, actor_id=uuid4())
    assert "PD3-V cannot be deleted" in str(refused.value)
    assert "2 goods receipts (GRN-A, GRN-B)" in str(refused.value)
    session.rollback()

    _purchase_bill(session, firm, vendor.id, first)
    with pytest.raises(ValidationError, match="1 goods receipt \\(GRN-B\\)"):
        service.bulk_delete(ids=[vendor.id], firm_scope=firm.id, actor_id=uuid4())
    session.rollback()
    session.refresh(vendor)
    assert vendor.is_deleted is False
    assert second.id is not None


def test_a_vendor_with_an_open_purchase_order_is_refused() -> None:
    """An approved order holds the supplier; a cancelled one does not."""
    session = _session()
    firm = _firm(session, "PD4")
    service = VendorService(session)
    busy = _vendor(session, firm, "PD4-BUSY")
    done = _vendor(session, firm, "PD4-DONE")
    _purchase_order(session, firm, busy.id, "PO-OPEN", "APPROVED")
    _purchase_order(session, firm, done.id, "PO-GONE", "CANCELLED")

    with pytest.raises(ValidationError, match="1 purchase order \\(PO-OPEN\\)"):
        service.delete(busy.id, firm_scope=firm.id, actor_id=uuid4())
    session.rollback()

    service.delete(done.id, firm_scope=firm.id, actor_id=uuid4())
    session.refresh(done)
    assert done.is_deleted is True
