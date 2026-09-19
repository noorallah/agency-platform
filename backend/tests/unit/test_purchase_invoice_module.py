"""Purchase invoice backend lifecycle and source-matching tests."""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.batch_serial.models import batch_serial as _batch_serial_models  # noqa: F401
from app.branches.models import Branch, Warehouse
from app.business.models import framework as _business_models  # noqa: F401
from app.common.audit.models import AuditLog
from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.customers.models import customer as _customer_models  # noqa: F401
from app.document_framework.models import DocumentTypeDefinition
from app.firms.models import Firm
from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
from app.identity.models import identity as _identity_models  # noqa: F401
from app.inventory.models import inventory as _inventory_models  # noqa: F401
from app.products.models import Product
from app.purchase.models import PurchaseOrder, PurchaseOrderLine
from app.purchase_invoice.models import PurchaseInvoice, PurchaseInvoiceLine
from app.purchase_invoice.schemas import (
    PurchaseInvoiceCreate,
    PurchaseInvoiceLineWrite,
    PurchaseInvoiceSourceType,
    PurchaseInvoiceStatus,
)
from app.purchase_invoice.services import PurchaseInvoiceService
from app.sales.models import territory as _sales_models  # noqa: F401
from app.tax.models import tax_framework as _tax_models  # noqa: F401
from app.uom.models import uom as _uom_models  # noqa: F401
from app.vendors.models import Vendor

# Fixtures here type their document numbers; see conftest (D-CFG-2).
pytestmark = pytest.mark.typed_document_numbers


def _session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _firm(session: Session) -> Firm:
    row = Firm(
        name="Invoice Firm",
        code="INV-FIRM",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(row)
    session.commit()
    return row


def _branch(session: Session, *, firm_id: UUID) -> Branch:
    row = Branch(
        firm_id=firm_id,
        code="BR-001",
        name="Branch BR-001",
        display_name="Branch BR-001",
        currency_code="INR",
        working_hours={"start": "09:00", "end": "18:00"},
        status="ACTIVE",
    )
    session.add(row)
    session.commit()
    return row


def _warehouse(session: Session, *, firm_id: UUID, branch_id: UUID) -> Warehouse:
    row = Warehouse(
        firm_id=firm_id,
        branch_id=branch_id,
        code="WH-001",
        name="Warehouse WH-001",
        display_name="Warehouse WH-001",
        status="ACTIVE",
    )
    session.add(row)
    session.commit()
    return row


def _vendor(session: Session, *, firm_id: UUID) -> Vendor:
    row = Vendor(
        firm_id=firm_id,
        code="VEN-001",
        name="Vendor VEN-001",
        display_name="Vendor VEN-001",
        status="ACTIVE",
    )
    session.add(row)
    session.commit()
    return row


def _product(session: Session, *, firm_id: UUID) -> Product:
    row = Product(
        firm_id=firm_id,
        code="SKU-001",
        name="Product SKU-001",
        product_type="STOCK_ITEM",
        status="ACTIVE",
    )
    session.add(row)
    session.commit()
    return row


def _purchase_order(
    session: Session,
    *,
    firm_id: UUID,
    vendor_id: UUID,
    branch_id: UUID,
    warehouse_id: UUID,
) -> PurchaseOrder:
    row = PurchaseOrder(
        firm_id=firm_id,
        branch_id=branch_id,
        warehouse_id=warehouse_id,
        vendor_id=vendor_id,
        po_number="PO-2026-000001",
        purchase_date=date(2026, 8, 2),
        status="APPROVED",
    )
    session.add(row)
    session.flush()
    line = PurchaseOrderLine(
        purchase_order_id=row.id,
        firm_id=firm_id,
        line_number=1,
        product_id=_product(session, firm_id=firm_id).id,
        ordered_quantity=Decimal("10"),
        free_quantity=Decimal("0"),
        base_quantity=Decimal("10"),
        unit_price=Decimal("100"),
        discount_percent=Decimal("0"),
        discount_amount=Decimal("0"),
        gross_amount=Decimal("1000"),
        tax_amount=Decimal("0"),
        net_amount=Decimal("1000"),
        status="ORDERED",
    )
    session.add(line)
    session.commit()
    return row


def _received(
    session: Session, po_line: PurchaseOrderLine
) -> tuple[GoodsReceipt, GoodsReceiptLine]:
    """Record the whole order line as received, on a completed receipt.

    Built as rows rather than through the receipt service so no stock or
    journal moves: these cases are about the bill, and a bill is raised
    against a receipt (D-BUY-14).
    """
    order = session.get(PurchaseOrder, po_line.purchase_order_id)
    assert order is not None
    receipt = GoodsReceipt(
        firm_id=order.firm_id,
        purchase_order_id=order.id,
        purchase_order_number=order.po_number,
        vendor_id=order.vendor_id,
        branch_id=order.branch_id,
        warehouse_id=order.warehouse_id,
        grn_number="GRN-2026-000001",
        receipt_date=date(2026, 8, 2),
        status="COMPLETED",
    )
    session.add(receipt)
    session.flush()
    line = GoodsReceiptLine(
        goods_receipt_id=receipt.id,
        firm_id=order.firm_id,
        line_number=1,
        purchase_order_line_id=po_line.id,
        purchase_order_line_number=po_line.line_number,
        product_id=po_line.product_id,
        ordered_quantity=po_line.ordered_quantity,
        current_receipt_quantity=po_line.ordered_quantity,
        accepted_quantity=po_line.ordered_quantity,
        unit_price=po_line.unit_price,
        warehouse_id=order.warehouse_id,
    )
    session.add(line)
    session.commit()
    return receipt, line


def test_purchase_invoice_creates_lifecycle_setup() -> None:
    """Billing a goods receipt builds the document type on first use.

    The type, its states and its numbering are created the first time a
    bill is raised. This used to bill the purchase order directly, a path
    that no longer exists (D-BUY-14).
    """
    session_factory = _session_factory()
    session = session_factory()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    vendor = _vendor(session, firm_id=firm.id)
    purchase_order = _purchase_order(
        session,
        firm_id=firm.id,
        vendor_id=vendor.id,
        branch_id=branch.id,
        warehouse_id=warehouse.id,
    )
    po_line = session.scalar(
        select(PurchaseOrderLine).where(
            PurchaseOrderLine.purchase_order_id == purchase_order.id
        )
    )
    assert po_line is not None
    receipt, receipt_line = _received(session, po_line)

    service = PurchaseInvoiceService(session)
    row = service.create_invoice(
        PurchaseInvoiceCreate(
            supplier_invoice_number="SUP-1001",
            supplier_invoice_date=date(2026, 8, 2),
            invoice_date=date(2026, 8, 2),
            source_documents=[
                {
                    "source_document_type": PurchaseInvoiceSourceType.GOODS_RECEIPT,
                    "source_document_id": receipt.id,
                }
            ],
            lines=[
                PurchaseInvoiceLineWrite(
                    source_document_type=PurchaseInvoiceSourceType.GOODS_RECEIPT,
                    source_document_id=receipt.id,
                    source_document_line_id=receipt_line.id,
                    line_number=1,
                    current_invoice_quantity=Decimal("4"),
                    unit_price=Decimal("100"),
                    discount_amount=Decimal("0"),
                    charges_amount=Decimal("0"),
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=uuid4(),
    )

    response = service.invoice_response(row)
    assert response.status == PurchaseInvoiceStatus.DRAFT
    assert response.invoice_number.startswith("PI")
    assert response.grand_total == Decimal("400.0000")
    assert response.duplicate_warning is None
    assert (
        session.scalar(
            select(DocumentTypeDefinition).where(
                DocumentTypeDefinition.firm_id == firm.id,
                DocumentTypeDefinition.code == "PURCHASE_INVOICE",
            )
        )
        is not None
    )
    assert (
        session.scalar(select(PurchaseInvoice).where(PurchaseInvoice.id == row.id))
        is not None
    )
    assert (
        session.scalar(
            select(PurchaseInvoiceLine).where(
                PurchaseInvoiceLine.purchase_invoice_id == row.id
            )
        )
        is not None
    )
    assert service.summary(firm_scope=firm.id).total == 1
    assert session.scalar(select(AuditLog.id)) is not None


def test_an_invoice_line_with_no_price_bills_at_the_source_lines_price() -> None:
    """Silence takes the order or receipt line's price; a stated zero is zero.

    D-BUY-3, invoice half: the price defaulted to zero, so a bill sent without
    prices was worth nothing.
    """
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    vendor = _vendor(session, firm_id=firm.id)
    order = _purchase_order(
        session,
        firm_id=firm.id,
        vendor_id=vendor.id,
        branch_id=branch.id,
        warehouse_id=warehouse.id,
    )
    po_line = session.scalar(
        select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == order.id)
    )
    assert po_line is not None
    receipt, receipt_line = _received(session, po_line)

    def _bill(number: str, price: Decimal | None) -> PurchaseInvoiceLine:
        line: dict[str, object] = {
            "source_document_type": PurchaseInvoiceSourceType.GOODS_RECEIPT,
            "source_document_id": receipt.id,
            "source_document_line_id": receipt_line.id,
            "line_number": 1,
            "current_invoice_quantity": Decimal("2"),
        }
        if price is not None:
            line["unit_price"] = price
        row = PurchaseInvoiceService(session).create_invoice(
            PurchaseInvoiceCreate(
                supplier_invoice_number=number,
                supplier_invoice_date=date(2026, 8, 2),
                invoice_date=date(2026, 8, 2),
                source_documents=[
                    {
                        "source_document_type": (
                            PurchaseInvoiceSourceType.GOODS_RECEIPT
                        ),
                        "source_document_id": receipt.id,
                    }
                ],
                lines=[PurchaseInvoiceLineWrite.model_validate(line)],
            ),
            firm_id=firm.id,
            actor_id=uuid4(),
        )
        saved = session.scalar(
            select(PurchaseInvoiceLine).where(
                PurchaseInvoiceLine.purchase_invoice_id == row.id
            )
        )
        assert saved is not None
        return saved

    assert _bill("SUP-SILENT", None).unit_price == Decimal("100")
    assert _bill("SUP-ZERO", Decimal("0")).unit_price == Decimal("0")


def test_only_an_approved_bill_can_be_closed() -> None:
    """D-BUY-12: a DRAFT or CANCELLED bill could be closed.

    Driven on TEST01 on 2026-09-18: PI-2026-2027-000008 went from DRAFT to
    CLOSED, reading as finished business though it never posted.
    """
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    vendor = _vendor(session, firm_id=firm.id)
    order = _purchase_order(
        session,
        firm_id=firm.id,
        vendor_id=vendor.id,
        branch_id=branch.id,
        warehouse_id=warehouse.id,
    )
    po_line = session.scalar(
        select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == order.id)
    )
    assert po_line is not None
    receipt, receipt_line = _received(session, po_line)
    service = PurchaseInvoiceService(session)

    def _draft(number: str) -> PurchaseInvoice:
        return service.create_invoice(
            PurchaseInvoiceCreate(
                supplier_invoice_number=number,
                supplier_invoice_date=date(2026, 8, 2),
                invoice_date=date(2026, 8, 2),
                source_documents=[
                    {
                        "source_document_type": (
                            PurchaseInvoiceSourceType.GOODS_RECEIPT
                        ),
                        "source_document_id": receipt.id,
                    }
                ],
                lines=[
                    PurchaseInvoiceLineWrite(
                        source_document_type=PurchaseInvoiceSourceType.GOODS_RECEIPT,
                        source_document_id=receipt.id,
                        source_document_line_id=receipt_line.id,
                        line_number=1,
                        current_invoice_quantity=Decimal("1"),
                    )
                ],
            ),
            firm_id=firm.id,
            actor_id=uuid4(),
        )

    draft = _draft("SUP-DRAFT")
    with pytest.raises(ValidationError, match="Only approved purchase invoices"):
        service.close_invoice(draft.id, firm_scope=firm.id, actor_id=uuid4())

    cancelled = _draft("SUP-CANCELLED")
    service.cancel_invoice(cancelled.id, firm_scope=firm.id, actor_id=uuid4())
    with pytest.raises(ValidationError, match="Only approved purchase invoices"):
        service.close_invoice(cancelled.id, firm_scope=firm.id, actor_id=uuid4())


def test_a_bill_cannot_skip_the_receipt() -> None:
    """D-BUY-14: the request body used to carry a switch past the receipt.

    Driven 2026-09-19 on TEST01 (fixture ``po-approved``, suffix t0919d4tq):
    PO-TEST01-HO-2026-2027-000011 for ten, nothing received, billed with
    ``allow_direct_purchase_order`` true and approved -- 1,180 owed to the
    supplier, 1,000 of it booked as a price variance, nothing on the shelf.
    The field is gone, and a bill naming the order -- as its source or on a
    line -- is refused whatever the body says.
    """
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    vendor = _vendor(session, firm_id=firm.id)
    order = _purchase_order(
        session,
        firm_id=firm.id,
        vendor_id=vendor.id,
        branch_id=branch.id,
        warehouse_id=warehouse.id,
    )
    po_line = session.scalar(
        select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == order.id)
    )
    assert po_line is not None
    receipt, _ = _received(session, po_line)

    def _bill(
        source_id: UUID, line_type: PurchaseInvoiceSourceType
    ) -> dict[str, object]:
        source_type = (
            PurchaseInvoiceSourceType.GOODS_RECEIPT
            if source_id == receipt.id
            else PurchaseInvoiceSourceType.PURCHASE_ORDER
        )
        return PurchaseInvoiceCreate(
            supplier_invoice_number="SUP-DIRECT",
            supplier_invoice_date=date(2026, 8, 2),
            invoice_date=date(2026, 8, 2),
            source_documents=[
                {"source_document_type": source_type, "source_document_id": source_id}
            ],
            lines=[
                PurchaseInvoiceLineWrite(
                    source_document_type=line_type,
                    source_document_id=source_id,
                    source_document_line_id=po_line.id,
                    line_number=1,
                    current_invoice_quantity=Decimal("10"),
                )
            ],
        ).model_dump(mode="json")

    straight = _bill(order.id, PurchaseInvoiceSourceType.PURCHASE_ORDER)
    with pytest.raises(PydanticValidationError, match="allow_direct_purchase_order"):
        PurchaseInvoiceCreate.model_validate(
            {**straight, "allow_direct_purchase_order": True}
        )

    service = PurchaseInvoiceService(session)
    # Straight against the order, and a line naming the order behind a
    # receipt's back: both refused before anything is looked up.
    for body in (straight, _bill(receipt.id, PurchaseInvoiceSourceType.PURCHASE_ORDER)):
        with pytest.raises(ValidationError, match="never straight against"):
            service.create_invoice(
                PurchaseInvoiceCreate.model_validate(body),
                firm_id=firm.id,
                actor_id=uuid4(),
            )
    assert session.scalar(select(PurchaseInvoice.id)) is None


def test_a_bill_cannot_lift_its_own_cap() -> None:
    """D-BUY-15: the request body used to carry a switch for the cap.

    Driven 2026-09-19 on TEST01 (fixture ``po-received``, suffix t0919hv0b):
    PI-2026-2027-000010 for 60 against GRN-TEST01-HO-2026-2027-000020, a
    receipt of 6, with ``allow_over_invoice`` true -- created and approved at
    7,080.00 owed to the supplier for goods that never came in. Neither field
    is on the write schema any more, and the cap applies to every bill.
    """
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    vendor = _vendor(session, firm_id=firm.id)
    order = _purchase_order(
        session,
        firm_id=firm.id,
        vendor_id=vendor.id,
        branch_id=branch.id,
        warehouse_id=warehouse.id,
    )
    po_line = session.scalar(
        select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == order.id)
    )
    assert po_line is not None
    receipt, receipt_line = _received(session, po_line)
    body = PurchaseInvoiceCreate(
        supplier_invoice_number="SUP-OVER",
        supplier_invoice_date=date(2026, 8, 2),
        invoice_date=date(2026, 8, 2),
        source_documents=[
            {
                "source_document_type": PurchaseInvoiceSourceType.GOODS_RECEIPT,
                "source_document_id": receipt.id,
            }
        ],
        lines=[
            PurchaseInvoiceLineWrite(
                source_document_type=PurchaseInvoiceSourceType.GOODS_RECEIPT,
                source_document_id=receipt.id,
                source_document_line_id=receipt_line.id,
                line_number=1,
                current_invoice_quantity=Decimal("60"),
            )
        ],
    ).model_dump(mode="json")

    for field, value in (("allow_over_invoice", True), ("over_invoice_percent", 1000)):
        with pytest.raises(PydanticValidationError, match=field):
            PurchaseInvoiceCreate.model_validate({**body, field: value})

    # Without the switch the cap holds: ten were received, sixty cannot be
    # billed.
    with pytest.raises(ValidationError, match="exceeds the available source"):
        PurchaseInvoiceService(session).create_invoice(
            PurchaseInvoiceCreate.model_validate(body),
            firm_id=firm.id,
            actor_id=uuid4(),
        )
    # The request's session is rolled back on the refusal, as here.
    session.rollback()
    assert session.scalar(select(PurchaseInvoice.id)) is None


def _other_receipt_line(
    session: Session,
    receipt: GoodsReceipt,
    *,
    number: str,
    status: str,
    firm_id: UUID | None = None,
) -> GoodsReceiptLine:
    """Record a second receipt beside ``receipt`` and return its line.

    Same order line, so the only thing wrong with naming it from a line of
    ``receipt`` is that it is not ``receipt``'s line -- which is the case.
    """
    firm = firm_id or receipt.firm_id
    other = GoodsReceipt(
        firm_id=firm,
        purchase_order_id=receipt.purchase_order_id,
        purchase_order_number=receipt.purchase_order_number,
        vendor_id=receipt.vendor_id,
        branch_id=receipt.branch_id,
        warehouse_id=receipt.warehouse_id,
        grn_number=number,
        receipt_date=date(2026, 8, 2),
        status=status,
    )
    session.add(other)
    session.flush()
    template = session.scalars(
        select(GoodsReceiptLine).where(GoodsReceiptLine.goods_receipt_id == receipt.id)
    ).one()
    line = GoodsReceiptLine(
        goods_receipt_id=other.id,
        firm_id=firm,
        line_number=1,
        purchase_order_line_id=template.purchase_order_line_id,
        purchase_order_line_number=template.purchase_order_line_number,
        product_id=template.product_id,
        ordered_quantity=template.ordered_quantity,
        current_receipt_quantity=template.current_receipt_quantity,
        accepted_quantity=template.accepted_quantity,
        unit_price=template.unit_price,
        warehouse_id=template.warehouse_id,
    )
    session.add(line)
    session.commit()
    return line


def test_a_bill_line_cannot_front_for_another_receipts_line() -> None:
    """D-BUY-17: a bill line was looked up by its id alone.

    Driven 2026-09-19 on TEST01: PI-2026-2027-000011 named the completed
    GRN-TEST01-HO-2026-2027-000020 (6) and carried the line id of the DRAFT
    GRN-TEST01-HO-2026-2027-000024 of another order -- 10 billed and
    approved, 1,180.00 owed for goods nobody had received. A line must be one
    of the named receipt's own lines, in the same firm, and a bill saved
    before the check cannot be approved through a line it does not own.
    """
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    vendor = _vendor(session, firm_id=firm.id)
    order = _purchase_order(
        session,
        firm_id=firm.id,
        vendor_id=vendor.id,
        branch_id=branch.id,
        warehouse_id=warehouse.id,
    )
    po_line = session.scalar(
        select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == order.id)
    )
    assert po_line is not None
    receipt, receipt_line = _received(session, po_line)
    draft_line = _other_receipt_line(
        session, receipt, number="GRN-2026-000002", status="DRAFT"
    )
    elsewhere = Firm(
        name="Elsewhere",
        code="ELSEWHERE",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(elsewhere)
    session.commit()
    foreign_line = _other_receipt_line(
        session,
        receipt,
        number="GRN-2026-000003",
        status="COMPLETED",
        firm_id=elsewhere.id,
    )
    service = PurchaseInvoiceService(session)

    def _bill(line_id: UUID, number: str) -> PurchaseInvoiceCreate:
        return PurchaseInvoiceCreate(
            supplier_invoice_number=number,
            supplier_invoice_date=date(2026, 8, 2),
            invoice_date=date(2026, 8, 2),
            source_documents=[
                {
                    "source_document_type": PurchaseInvoiceSourceType.GOODS_RECEIPT,
                    "source_document_id": receipt.id,
                }
            ],
            lines=[
                PurchaseInvoiceLineWrite(
                    source_document_type=PurchaseInvoiceSourceType.GOODS_RECEIPT,
                    source_document_id=receipt.id,
                    source_document_line_id=line_id,
                    line_number=1,
                    current_invoice_quantity=Decimal("4"),
                )
            ],
        )

    for line_id in (draft_line.id, foreign_line.id):
        with pytest.raises(ValidationError, match="GRN-2026-000001 has no line"):
            service.create_invoice(
                _bill(line_id, "SUP-FRONT"), firm_id=firm.id, actor_id=uuid4()
            )
        session.rollback()
    assert session.scalar(select(PurchaseInvoice.id)) is None

    # A bill saved before the check, pointing at the draft receipt's line, is
    # not approved.
    saved = service.create_invoice(
        _bill(receipt_line.id, "SUP-SAVED"), firm_id=firm.id, actor_id=uuid4()
    )
    line = session.scalars(
        select(PurchaseInvoiceLine).where(
            PurchaseInvoiceLine.purchase_invoice_id == saved.id
        )
    ).one()
    line.source_document_line_id = draft_line.id
    session.commit()
    with pytest.raises(ValidationError, match="GRN-2026-000001 has no line"):
        service.approve_invoice(saved.id, firm_scope=firm.id, actor_id=uuid4())
