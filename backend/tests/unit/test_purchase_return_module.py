"""Purchase return backend lifecycle and source-matching tests."""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.branches.models import Branch, Warehouse
from app.common.audit.models import AuditLog
from app.business.models import framework as _business_models  # noqa: F401
from app.batch_serial.models import batch_serial as _batch_serial_models  # noqa: F401
from app.customers.models import customer as _customer_models  # noqa: F401
from app.core.database.base import Base
from app.document_framework.models import DocumentTypeDefinition
from app.firms.models import Firm
from app.identity.models import identity as _identity_models  # noqa: F401
from app.inventory.models import inventory as _inventory_models  # noqa: F401
from app.products.models import Product
from app.purchase.models import PurchaseOrder, PurchaseOrderLine
from app.purchase_return.models import PurchaseReturn, PurchaseReturnLine
from app.purchase_return.schemas import (
    PurchaseReturnCreate,
    PurchaseReturnLineWrite,
    PurchaseReturnSourceType,
    PurchaseReturnStatus,
)
from app.purchase_return.services import PurchaseReturnService
from app.sales.models import territory as _sales_models  # noqa: F401
from app.tax.models import tax_framework as _tax_models  # noqa: F401
from app.vendors.models import Vendor
from app.uom.models import uom as _uom_models  # noqa: F401


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
        name="Return Firm",
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


def test_purchase_return_direct_po_return_creates_lifecycle_setup() -> None:
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
        select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == purchase_order.id)
    )
    assert po_line is not None

    service = PurchaseReturnService(session)
    row = service.create_return(
        PurchaseReturnCreate(
            supplier_return_number="SUP-1001",
            supplier_return_date=date(2026, 8, 2),
            return_date=date(2026, 8, 2),
            warehouse_id=warehouse.id,
            allow_direct_purchase_order=True,
            source_documents=[
                {
                    "source_document_type": PurchaseReturnSourceType.PURCHASE_ORDER,
                    "source_document_id": purchase_order.id,
                }
            ],
            lines=[
                PurchaseReturnLineWrite(
                    source_document_type=PurchaseReturnSourceType.PURCHASE_ORDER,
                    source_document_id=purchase_order.id,
                    source_document_line_id=po_line.id,
                    line_number=1,
                    current_return_quantity=Decimal("4"),
                    unit_price=Decimal("100"),
                    discount_amount=Decimal("0"),
                    charges_amount=Decimal("0"),
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=uuid4(),
    )

    response = service.return_response(row)
    assert response.status == PurchaseReturnStatus.DRAFT
    assert response.return_number.startswith("PR")
    assert response.grand_total == Decimal("400.0000")
    assert response.duplicate_warning is None
    assert session.scalar(
        select(DocumentTypeDefinition).where(
            DocumentTypeDefinition.firm_id == firm.id,
            DocumentTypeDefinition.code == "PURCHASE_RETURN",
        )
    ) is not None
    assert session.scalar(select(PurchaseReturn).where(PurchaseReturn.id == row.id)) is not None
    assert session.scalar(select(PurchaseReturnLine).where(PurchaseReturnLine.purchase_return_id == row.id)) is not None
    assert service.summary(firm_scope=firm.id).total == 1
    assert session.scalar(select(AuditLog.id)) is not None
