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
from app.business.models import BusinessProfile
from app.business.models import framework as _business_models  # noqa: F401
from app.common.audit.models import AuditLog
from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.customers.models import customer as _customer_models  # noqa: F401
from app.document_framework.models import DocumentTypeDefinition
from app.finance.models import JournalEntry, JournalLine, LedgerAccount
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm
from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
from app.identity.models import identity as _identity_models  # noqa: F401
from app.inventory.models import inventory as _inventory_models  # noqa: F401
from app.products.models import Product
from app.purchase.models import PurchaseOrder, PurchaseOrderLine
from app.purchase_invoice.models import (
    PurchaseInvoice,
    PurchaseInvoiceLine,
    PurchaseInvoiceLineTax,
)
from app.purchase_invoice.schemas import (
    PurchaseInvoiceCreate,
    PurchaseInvoiceLineWrite,
    PurchaseInvoiceSourceType,
    PurchaseInvoiceStatus,
)
from app.purchase_invoice.services import PurchaseInvoiceService
from app.purchase_return.schemas import (
    PurchaseReturnCreate,
    PurchaseReturnLineWrite,
    PurchaseReturnSourceType,
)
from app.purchase_return.services import PurchaseReturnService
from app.sales.models import GeoCountry
from app.sales.models import territory as _sales_models  # noqa: F401
from app.tax.models import TaxProfile
from app.tax.models import tax_framework as _tax_models  # noqa: F401
from app.tax.schemas import (
    TaxComponentWrite,
    TaxProfileWrite,
    TaxRuleWrite,
    TaxSystemWrite,
)
from app.tax.services.tax_framework_service import TaxFrameworkService
from app.tax.services.tax_rule_service import TaxRuleService
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


def test_the_reconciliation_counts_the_bills_that_still_stand() -> None:
    """One row per received line over live bills; a cancelled bill billed nothing.

    The report answered one row per invoice line carrying the quantities
    snapshotted when the line was written, so a receipt billed twice appeared
    twice with the older `pending` stale, and a cancelled bill's line still
    claimed its quantity billed with `pending` 0 -- PI-2026-2027-000014,
    cancelled, still 4 billed, 0 pending on TEST01 (D-RPT-13).
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

    def bill(number: str, quantity: str) -> PurchaseInvoice:
        return service.create_invoice(
            PurchaseInvoiceCreate(
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
                        source_document_line_id=receipt_line.id,
                        line_number=1,
                        current_invoice_quantity=Decimal(quantity),
                    )
                ],
            ),
            firm_id=firm.id,
            actor_id=uuid4(),
        )

    def row() -> tuple[Decimal, Decimal, Decimal, int]:
        [record] = service.reconciliation_report(firm_scope=firm.id)
        return (
            record.invoiced_quantity,
            record.draft_quantity,
            record.pending_quantity,
            len(record.invoice_numbers.split(", ")),
        )

    seed_finance_setup(
        session, firm_id=firm.id, year_starts_on=date(2026, 4, 1), actor_id=uuid4()
    )
    received = receipt_line.current_receipt_quantity
    first = bill("SUP-1", "3")
    second = bill("SUP-2", "2")
    assert row() == (Decimal("0.00"), Decimal("5.00"), received - 5, 2)

    service.approve_invoice(first.id, firm_scope=firm.id, actor_id=uuid4())
    assert row() == (Decimal("3.00"), Decimal("2.00"), received - 5, 2)

    service.cancel_invoice(second.id, firm_scope=firm.id, actor_id=uuid4())
    assert row() == (Decimal("3.00"), Decimal("0.00"), received - 3, 1)

    # D-RPT-17: the grid derives its columns from the row, so the register
    # answered a supplier and a branch as UUIDs and the reconciliation a
    # product as one. Each id keeps its name beside it.
    entry = service.register_report(firm_scope=firm.id)[0]
    assert (entry.vendor_id, entry.vendor_name) == (vendor.id, vendor.display_name)
    assert (entry.branch_id, entry.branch_name) == (branch.id, branch.name)
    product = session.scalar(select(Product).where(Product.firm_id == firm.id))
    assert product is not None
    [reconciled] = service.reconciliation_report(firm_scope=firm.id)
    assert reconciled.product_id == product.id
    assert (reconciled.product_code, reconciled.product_name) == (
        product.code,
        product.name,
    )


def _gst_profile(session: Session, *, firm: Firm, actor_id: UUID) -> TaxProfile:
    """Return an 18% tax split into two 9% components, the way GST is charged."""
    country = GeoCountry(
        code="IN",
        name="India",
        iso2="IN",
        iso3="IND",
        phone_code="+91",
        is_active=True,
        created_by=actor_id,
        updated_by=actor_id,
    )
    business_profile = BusinessProfile(
        code="GENERIC",
        name="Generic",
        industry_type="GENERIC",
        status="ACTIVE",
        is_default=True,
        created_by=actor_id,
        updated_by=actor_id,
        default_settings={},
    )
    session.add_all([country, business_profile])
    session.commit()

    framework = TaxFrameworkService(session)
    system = framework.create_system(
        TaxSystemWrite(
            country_id=country.id, code="GST", name="Goods and Services Tax"
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    components = [
        framework.create_component(
            TaxComponentWrite(
                tax_system_id=system.id,
                code=code,
                name=name,
                label=name,
                percentage="9",
            ),
            firm_id=firm.id,
            actor_id=actor_id,
        )
        for code, name in (("CGST", "Central GST"), ("SGST", "State GST"))
    ]
    profile = framework.create_profile(
        TaxProfileWrite(
            tax_system_id=system.id,
            business_profile_id=business_profile.id,
            code="GST_18_LOCAL",
            name="GST 18 local",
            components=[
                {
                    "tax_component_id": component.id,
                    "percentage": "9",
                    "calculation_order": order,
                    # Input GST is claimable, and the bill has to say so per
                    # component: that flag is what the ITC split will read.
                    "recoverable": True,
                }
                for order, component in enumerate(components, start=1)
            ],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    TaxRuleService(session).create_rule(
        TaxRuleWrite(
            country_id=country.id,
            business_profile_id=business_profile.id,
            code="PURCHASE_DEFAULT",
            name="Purchase default",
            priority=50,
            status="ACTIVE",
            actions=[
                {
                    "sequence": 1,
                    "action_type": "APPLY_TAX_PROFILE",
                    "target_tax_profile_id": profile.id,
                }
            ],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    return profile


def _stored_components(
    session: Session, invoice: PurchaseInvoice
) -> list[PurchaseInvoiceLineTax]:
    """Return every tax component row hanging off the bill's lines, in order."""
    return list(
        session.scalars(
            select(PurchaseInvoiceLineTax)
            .join(
                PurchaseInvoiceLine,
                PurchaseInvoiceLine.id
                == PurchaseInvoiceLineTax.purchase_invoice_line_id,
            )
            .where(PurchaseInvoiceLine.purchase_invoice_id == invoice.id)
            .order_by(PurchaseInvoiceLineTax.sequence.asc())
        ).all()
    )


def test_a_bill_line_keeps_the_tax_it_was_charged_component_by_component() -> None:
    """One `tax_amount` cannot be split into IGST against CGST and SGST.

    D-CMP-20: GSTR-3B claims input credit per head and the ledger carries each
    component to its own input-tax account, and neither can be derived from
    one total. The breakup the rule engine computed was discarded at save
    time, surviving only in `tax_rule_execution_logs`, which the retention
    job prunes -- and rules are effective-dated, so asking the engine again
    later can answer differently from what the supplier charged. The sales
    invoice keeps its breakup in `sales_invoice_line_taxes`; the bill keeps
    its own the same way, and an edit rebuilds it rather than orphaning it.
    """
    session = _session_factory()()
    actor_id = uuid4()
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
    profile = _gst_profile(session, firm=firm, actor_id=actor_id)
    # The product names the group; the line names nothing, so the profile the
    # bill records is the one the service resolved rather than one it was sent.
    product = session.get(Product, po_line.product_id)
    assert product is not None
    product.tax_profile_group_code = "GST_18_LOCAL"
    session.commit()

    def _bill(quantity: Decimal) -> PurchaseInvoiceCreate:
        """Bill `quantity` of the received line at 100 each, naming no profile."""
        return PurchaseInvoiceCreate(
            supplier_invoice_number="SUP-GST-1",
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
                    current_invoice_quantity=quantity,
                    unit_price=Decimal("100"),
                )
            ],
        )

    service = PurchaseInvoiceService(session)
    invoice = service.create_invoice(
        _bill(Decimal("4")), firm_id=firm.id, actor_id=actor_id
    )

    stored = _stored_components(session, invoice)
    assert [row.component_code for row in stored] == ["CGST", "SGST"]
    assert [row.percentage for row in stored] == [Decimal("9.0000"), Decimal("9.0000")]
    assert [row.amount for row in stored] == [Decimal("36.0000"), Decimal("36.0000")]
    assert {row.base_amount for row in stored} == {Decimal("400.0000")}
    assert all(row.recoverable for row in stored)
    assert all(row.firm_id == firm.id for row in stored)
    line = session.scalar(
        select(PurchaseInvoiceLine).where(
            PurchaseInvoiceLine.purchase_invoice_id == invoice.id
        )
    )
    assert line is not None
    assert sum(row.amount for row in stored) == line.tax_amount == Decimal("72.0000")
    assert invoice.tax_total == Decimal("72.0000")
    assert line.tax_profile_id == profile.id, (
        "the line records the profile that produced the tax, though the "
        "caller named none"
    )

    response = service.invoice_response(invoice)
    assert response.lines[0].tax_amount == Decimal("72.0000")
    assert [item.component_code for item in response.lines[0].taxes] == [
        "CGST",
        "SGST",
    ]
    assert sum(item.amount for item in response.lines[0].taxes) == Decimal("72.0000")

    # An edit rebuilds the lines; the old components must go with them rather
    # than linger against a line id nothing references any more.
    service.update_invoice(
        invoice.id, _bill(Decimal("2")), firm_scope=firm.id, actor_id=actor_id
    )
    every_component = list(session.scalars(select(PurchaseInvoiceLineTax)).all())
    live_line_ids = set(
        session.scalars(
            select(PurchaseInvoiceLine.id).where(
                PurchaseInvoiceLine.purchase_invoice_id == invoice.id
            )
        ).all()
    )
    assert len(live_line_ids) == 1
    assert {row.purchase_invoice_line_id for row in every_component} == live_line_ids
    assert sorted(row.amount for row in every_component) == [
        Decimal("18.0000"),
        Decimal("18.0000"),
    ]
    assert sum(row.amount for row in _stored_components(session, invoice)) == Decimal(
        "36.0000"
    )


def _postings(
    session: Session, *, module: str, source_id: UUID
) -> dict[str, tuple[Decimal, Decimal]]:
    """Return (debit, credit) per ledger account code for one document's journal."""
    rows = session.execute(
        select(LedgerAccount.code, JournalLine.debit_amount, JournalLine.credit_amount)
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
        .join(LedgerAccount, LedgerAccount.id == JournalLine.ledger_account_id)
        .where(
            JournalEntry.source_module == module,
            JournalEntry.source_id == source_id,
            JournalEntry.is_deleted.is_(False),
            JournalEntry.reversal_of_id.is_(None),
        )
    ).all()
    totals: dict[str, tuple[Decimal, Decimal]] = {}
    for code, debit, credit in rows:
        d, c = totals.get(code, (Decimal("0"), Decimal("0")))
        totals[code] = (d + Decimal(str(debit)), c + Decimal(str(credit)))
    return totals


def _bill_of(
    receipt: GoodsReceipt,
    receipt_line: GoodsReceiptLine,
    *,
    number: str,
    quantity: str,
    on: date,
) -> PurchaseInvoiceCreate:
    """Bill `quantity` of the received line at 100 each, naming no profile."""
    return PurchaseInvoiceCreate(
        supplier_invoice_number=number,
        supplier_invoice_date=on,
        invoice_date=on,
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
                current_invoice_quantity=Decimal(quantity),
                unit_price=Decimal("100"),
            )
        ],
    )


def test_input_tax_posts_one_leg_per_gst_head_and_reverses_the_same_way() -> None:
    """The ledger claims the credit head by head, as GSTR-3B does (D-CMP-20).

    A bill's input tax posted to 1300 as one total, so the IGST claimed could
    not be told from the CGST and SGST. Each component now posts to its own
    head through `input_tax_purpose`; a return raised off the bill reverses
    the same heads in the bill line's proportions; a bill whose lines kept no
    rows -- one written before they existed -- still posts the total to 1300.
    """
    session = _session_factory()()
    actor_id = uuid4()
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
    _gst_profile(session, firm=firm, actor_id=actor_id)
    product = session.get(Product, po_line.product_id)
    assert product is not None
    product.tax_profile_group_code = "GST_18_LOCAL"
    session.commit()
    seed_finance_setup(
        session, firm_id=firm.id, year_starts_on=date(2026, 4, 1), actor_id=actor_id
    )
    bills = PurchaseInvoiceService(session)
    bill = bills.create_invoice(
        _bill_of(
            receipt, receipt_line, number="SUP-HEADS", quantity="4", on=date(2026, 8, 2)
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    bills.approve_invoice(bill.id, firm_scope=firm.id, actor_id=actor_id)
    session.commit()

    posted = _postings(session, module="purchase_invoice", source_id=bill.id)
    assert posted["1320"] == (Decimal("36.00"), Decimal("0.00")), "CGST to its head"
    assert posted["1330"] == (Decimal("36.00"), Decimal("0.00")), "SGST to its head"
    assert "1300" not in posted, "nothing left on the undivided account"
    assert posted["2100"][1] == Decimal("472.00")

    # Two of the four go back, off the bill's line: half of each head reversed.
    bill_line = session.scalars(
        select(PurchaseInvoiceLine).where(
            PurchaseInvoiceLine.purchase_invoice_id == bill.id
        )
    ).one()
    returns = PurchaseReturnService(session)
    sent_back = returns.create_return(
        PurchaseReturnCreate(
            return_date=date(2026, 8, 3),
            warehouse_id=warehouse.id,
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
                    current_return_quantity=Decimal("2"),
                    warehouse_id=warehouse.id,
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    returns.approve_return(sent_back.id, firm_scope=firm.id, actor_id=actor_id)
    returns.complete_return(sent_back.id, firm_scope=firm.id, actor_id=actor_id)
    session.commit()
    reversed_ = _postings(session, module="purchase_return", source_id=sent_back.id)
    assert reversed_["1320"] == (Decimal("0.00"), Decimal("18.00"))
    assert reversed_["1330"] == (Decimal("0.00"), Decimal("18.00"))
    assert "1300" not in reversed_

    # A bill whose lines kept no rows still posts its total to 1300.
    second = bills.create_invoice(
        _bill_of(
            receipt, receipt_line, number="SUP-OLD", quantity="2", on=date(2026, 8, 4)
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    bills._delete_line_taxes(second.id)
    session.commit()
    bills.approve_invoice(second.id, firm_scope=firm.id, actor_id=actor_id)
    session.commit()
    undivided = _postings(session, module="purchase_invoice", source_id=second.id)
    assert undivided["1300"] == (Decimal("36.00"), Decimal("0.00"))
    assert "1320" not in undivided
    assert "1330" not in undivided


def test_the_register_takes_a_window_and_a_page() -> None:
    """D-RPT-18: the register was every bill the firm ever entered.

    Read on the bill's own `invoice_date`, both ends inclusive, with
    `total_records` counting the matches rather than the page. Pending,
    overdue, outstanding and the reconciliation are what is open today, so
    they take neither.
    """
    from app.purchase_invoice.api.router import purchase_invoice_register, router
    from tests.unit.report_windows import assert_page_size_is_bounded, report_scope

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
    days = [date(2026, 8, 2), date(2026, 8, 3), date(2026, 8, 4)]
    for number, day in enumerate(days):
        service.create_invoice(
            PurchaseInvoiceCreate(
                supplier_invoice_number=f"SUP-W{number}",
                supplier_invoice_date=day,
                invoice_date=day,
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
                        current_invoice_quantity=Decimal("1"),
                    )
                ],
            ),
            firm_id=firm.id,
            actor_id=uuid4(),
        )
    scope = report_scope(firm.id)

    page = purchase_invoice_register(
        scope=scope,
        db=session,
        from_date=days[1],
        to_date=days[2],
        page=1,
        page_size=1,
    )
    assert page.pagination.total_records == 2
    assert [row.invoice_date for row in page.data] == [days[2]]

    assert_page_size_is_bounded(router, "/api/v1/purchase-invoices/reports/register")
