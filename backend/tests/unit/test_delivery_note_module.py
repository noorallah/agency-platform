"""Delivery note backend lifecycle and inventory-dispatch tests."""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.branches.models import Branch, Warehouse
from app.business.models import framework as _business_models  # noqa: F401
from app.batch_serial.models import batch_serial as _batch_serial_models  # noqa: F401
from app.common.audit.models import AuditLog
from app.core.database.base import Base
from app.customers.models import Customer
from app.delivery_note.models import DeliveryNote
from app.delivery_note.schemas import DeliveryNoteCreate, DeliveryNoteLineWrite, DeliveryNoteStatus
from app.delivery_note.services import DeliveryNoteService
from app.document_framework.models import DocumentTypeDefinition
from app.firms.models import Firm
from app.identity.models import identity as _identity_models  # noqa: F401
from app.inventory.models import InventoryTransaction
from app.inventory.models import inventory as _inventory_models  # noqa: F401
from app.inventory.schemas import InventoryAdjustmentCreate
from app.inventory.services import InventoryService
from app.products.models import Product
from app.sales.models import territory as _sales_models  # noqa: F401
from app.sales_order.models import SalesOrderLine
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services import SalesOrderService
from app.tax.models import tax_framework as _tax_models  # noqa: F401
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
        name="Delivery Firm",
        code="DLV-FIRM",
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


def _customer(session: Session, *, firm_id: UUID) -> Customer:
    row = Customer(
        firm_id=firm_id,
        code="CUS-001",
        customer_type="RETAIL",
        name="Customer CUS-001",
        display_name="Customer CUS-001",
        currency_code="INR",
        status="ACTIVE",
        credit_limit=Decimal("50000"),
        opening_balance=Decimal("1000"),
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


def test_delivery_note_creates_lifecycle_and_dispatches_inventory() -> None:
    session_factory = _session_factory()
    session = session_factory()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    customer = _customer(session, firm_id=firm.id)
    product = _product(session, firm_id=firm.id)
    actor_id = uuid4()

    InventoryService(session).create_adjustment(
        InventoryAdjustmentCreate(
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            product_id=product.id,
            quantity=Decimal("10"),
            reference_number="ADJ-1",
            reference_type="ADJUSTMENT",
            transaction_date=date(2026, 8, 3),
        ),
        firm_scope=firm.id,
        actor_id=actor_id,
    )

    sales_service = SalesOrderService(session)
    order = sales_service.create_order(
        SalesOrderCreate(
            customer_id=customer.id,
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            order_date=date(2026, 8, 3),
            lines=[
                SalesOrderLineWrite(
                    line_number=1,
                    product_id=product.id,
                    quantity=Decimal("4"),
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    approved_order = sales_service.approve_order(order.id, firm_scope=firm.id, actor_id=actor_id)
    source_line = session.scalar(select(SalesOrderLine).where(SalesOrderLine.sales_order_id == approved_order.id))
    assert source_line is not None

    service = DeliveryNoteService(session)
    row = service.create_note(
        DeliveryNoteCreate(
            sales_order_id=approved_order.id,
            delivery_date=date(2026, 8, 4),
            lines=[
                DeliveryNoteLineWrite(
                    sales_order_line_id=source_line.id,
                    line_number=1,
                    current_delivery_quantity=Decimal("4"),
                    free_quantity=Decimal("0"),
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )

    response = service.note_response(row)
    assert response.status == DeliveryNoteStatus.DRAFT
    assert response.delivery_note_number.startswith("DN")
    assert response.grand_total == Decimal("400.0000")
    assert session.scalar(
        select(DocumentTypeDefinition).where(
            DocumentTypeDefinition.firm_id == firm.id,
            DocumentTypeDefinition.code == "DELIVERY_NOTE",
        )
    ) is not None
    assert session.scalar(select(DeliveryNote).where(DeliveryNote.id == row.id)) is not None

    approved_note = service.approve_note(row.id, firm_scope=firm.id, actor_id=actor_id)
    dispatched_note = service.dispatch_note(approved_note.id, firm_scope=firm.id, actor_id=actor_id)
    assert dispatched_note.status == DeliveryNoteStatus.DISPATCHED.value
    released = session.scalar(
        select(InventoryTransaction).where(
            InventoryTransaction.reference_type == "SALES_ORDER",
            InventoryTransaction.reference_number == approved_order.order_number,
            InventoryTransaction.transaction_type == "UNRESERVE",
        )
    )
    dispatched = session.scalar(
        select(InventoryTransaction).where(
            InventoryTransaction.reference_type == "DELIVERY_NOTE",
            InventoryTransaction.reference_number == dispatched_note.delivery_note_number,
            InventoryTransaction.transaction_type == "DISPATCH",
        )
    )
    assert released is not None
    assert released.reserved_quantity_delta == Decimal("-4.0000")
    assert dispatched is not None
    assert dispatched.current_quantity_delta == Decimal("-4.0000")
    assert service.summary(firm_scope=firm.id).total == 1
    assert session.scalar(select(AuditLog.id)) is not None
