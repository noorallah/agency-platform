"""Delivery note backend lifecycle and inventory-dispatch tests."""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.batch_serial.models import batch_serial as _batch_serial_models  # noqa: F401
from app.branches.models import Branch, Warehouse
from app.business.models import BusinessFeature, BusinessProfile, ProfileFeature
from app.business.models import framework as _business_models  # noqa: F401
from app.common.audit.models import AuditLog
from app.core.database.base import Base
from app.core.exceptions import AuthorizationError
from app.customers.models import Customer
from app.delivery_note.models import DeliveryNote
from app.delivery_note.schemas import (
    DeliveryNoteCreate,
    DeliveryNoteLineWrite,
    DeliveryNoteStatus,
)
from app.delivery_note.services import DeliveryNoteService
from app.document_framework.models import DocumentTypeDefinition
from app.firms.models import Firm
from app.identity.models import identity as _identity_models  # noqa: F401
from app.inventory.models import InventoryTransaction
from app.inventory.models import inventory as _inventory_models  # noqa: F401
from app.inventory.schemas import InventoryAdjustmentCreate
from app.inventory.services import InventoryService
from app.products.models import Product
from app.sales.models import SalesTerritoryNode, TerritoryRouteProfile
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
    """A note raised from an approved order dispatches the stock it names."""
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
    approved_order = sales_service.approve_order(
        order.id, firm_scope=firm.id, actor_id=actor_id
    )
    source_line = session.scalar(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == approved_order.id)
    )
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
    assert (
        session.scalar(
            select(DocumentTypeDefinition).where(
                DocumentTypeDefinition.firm_id == firm.id,
                DocumentTypeDefinition.code == "DELIVERY_NOTE",
            )
        )
        is not None
    )
    assert (
        session.scalar(select(DeliveryNote).where(DeliveryNote.id == row.id))
        is not None
    )

    approved_note = service.approve_note(row.id, firm_scope=firm.id, actor_id=actor_id)
    dispatched_note = service.dispatch_note(
        approved_note.id, firm_scope=firm.id, actor_id=actor_id
    )
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
            InventoryTransaction.reference_number
            == dispatched_note.delivery_note_number,
            InventoryTransaction.transaction_type == "DISPATCH",
        )
    )
    assert released is not None
    assert released.reserved_quantity_delta == Decimal("-4.0000")
    assert dispatched is not None
    assert dispatched.current_quantity_delta == Decimal("-4.0000")
    assert service.summary(firm_scope=firm.id).total == 1
    assert session.scalar(select(AuditLog.id)) is not None


def test_delivery_by_route_labels_the_route_without_crashing() -> None:
    """A route profile has no name of its own; the territory carries it.

    ``by_route_report`` read ``TerritoryRouteProfile.name``, which does not
    exist -- the model is a one-to-one extension of a territory and holds only
    the route-specific fields. Every firm with a route on any delivery note got
    an AttributeError from this report, and mypy had been saying so the whole
    time.
    """
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    customer = _customer(session, firm_id=firm.id)
    product = _product(session, firm_id=firm.id)
    actor_id = uuid4()

    territory = SalesTerritoryNode(
        firm_id=firm.id,
        hierarchy_level_id=uuid4(),
        code="RT-01",
        name="North City Route",
        path="RT-01",
    )
    session.add(territory)
    session.flush()
    # A route profile carries no firm of its own; it belongs to its territory.
    profile = TerritoryRouteProfile(territory_id=territory.id)
    session.add(profile)
    session.commit()

    InventoryService(session).create_adjustment(
        InventoryAdjustmentCreate(
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            product_id=product.id,
            quantity=Decimal("10"),
            reference_number="ADJ-ROUTE",
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
            route_id=profile.id,
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
    approved_order = sales_service.approve_order(
        order.id, firm_scope=firm.id, actor_id=actor_id
    )
    source_line = session.scalar(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == approved_order.id)
    )
    assert source_line is not None

    service = DeliveryNoteService(session)
    note = service.create_note(
        DeliveryNoteCreate(
            sales_order_id=approved_order.id,
            delivery_date=date(2026, 8, 4),
            lines=[
                DeliveryNoteLineWrite(
                    sales_order_line_id=source_line.id,
                    line_number=1,
                    current_delivery_quantity=Decimal("4"),
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    session.commit()
    assert note.route_id == profile.id

    rows = service.by_route_report(firm_scope=firm.id)

    assert len(rows) == 1
    assert rows[0].dimension_id == profile.id
    assert rows[0].dimension_name == "North City Route"


def _profile_without_vehicle_tracking(session: Session) -> None:
    """Seed a default profile that does not enable VEHICLE_TRACKING."""
    profile = BusinessProfile(
        code="GENERIC",
        name="Generic",
        industry_type="GENERIC",
        status="ACTIVE",
        is_default=True,
    )
    feature = BusinessFeature(code="VEHICLE_TRACKING", name="Vehicle Tracking")
    session.add_all([profile, feature])
    session.flush()
    session.add(
        ProfileFeature(
            business_profile_id=profile.id,
            feature_id=feature.id,
            is_enabled=False,
        )
    )
    session.commit()


def test_a_firm_without_vehicle_tracking_still_dispatches_goods() -> None:
    """The feature owns the vehicle fields, not the delivery note.

    Gating the endpoint would have stopped the firm dispatching anything
    because it does not record which van the goods went on.
    """
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    customer = _customer(session, firm_id=firm.id)
    product = _product(session, firm_id=firm.id)
    actor_id = uuid4()
    _profile_without_vehicle_tracking(session)

    InventoryService(session).create_adjustment(
        InventoryAdjustmentCreate(
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            product_id=product.id,
            quantity=Decimal("10"),
            reference_number="ADJ-VEH",
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
    approved = sales_service.approve_order(
        order.id, firm_scope=firm.id, actor_id=actor_id
    )
    source_line = session.scalar(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == approved.id)
    )
    assert source_line is not None

    def payload(**extra: str) -> DeliveryNoteCreate:
        return DeliveryNoteCreate(
            sales_order_id=approved.id,
            delivery_date=date(2026, 8, 4),
            lines=[
                DeliveryNoteLineWrite(
                    sales_order_line_id=source_line.id,
                    line_number=1,
                    current_delivery_quantity=Decimal("1"),
                    unit_price=Decimal("100"),
                )
            ],
            **extra,
        )

    service = DeliveryNoteService(session)

    # The note itself is fine.
    note = service.create_note(payload(), firm_id=firm.id, actor_id=actor_id)
    assert note.id is not None

    # Naming the van is not.
    with pytest.raises(AuthorizationError, match="VEHICLE_TRACKING"):
        service.create_note(
            payload(vehicle="KA-01-AB-1234"), firm_id=firm.id, actor_id=actor_id
        )
