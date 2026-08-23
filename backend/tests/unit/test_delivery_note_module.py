"""Delivery note backend lifecycle and inventory-dispatch tests."""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.batch_serial.models import batch_serial as _batch_serial_models  # noqa: F401
from app.batch_serial.models.batch_serial import BatchRecord
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
from app.inventory.models import InventoryRecord, InventoryTransaction
from app.inventory.models import inventory as _inventory_models  # noqa: F401
from app.inventory.schemas import InventoryAdjustmentCreate
from app.inventory.services import InventoryService
from app.products.models import Product
from app.sales.models import SalesTerritoryNode, TerritoryRouteProfile
from app.sales.models import territory as _sales_models  # noqa: F401
from app.sales_order.models import SalesOrder, SalesOrderLine
from app.sales_order.schemas import (
    SalesOrderCreate,
    SalesOrderLineWrite,
    SalesOrderStatus,
)
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


def test_a_line_larger_than_any_one_batch_still_dispatches() -> None:
    """Stock spread across batches is still stock.

    The availability gate read one row with ``scalar()``, and a product held in
    batches is as many rows as it has batches -- so it compared one batch's
    quantity against the whole line and refused it, while
    ``allocate_for_dispatch`` on the next line would have split it across both.
    Seeding batch-tracked history is what surfaced this: the two demo firms
    that trace their goods lost a third of their deliveries to it.
    """
    session_factory = _session_factory()
    session = session_factory()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    customer = _customer(session, firm_id=firm.id)
    product = _product(session, firm_id=firm.id)
    actor_id = uuid4()

    inventory = InventoryService(session)
    # A hundred on hand across three deliveries, and no single one of them
    # covering a line of forty-five.
    for batch_number, expiry, quantity in (
        ("MARCH", date(2027, 3, 31), "30"),
        ("JUNE", date(2027, 6, 30), "30"),
        ("SEPTEMBER", date(2027, 9, 30), "40"),
    ):
        batch = BatchRecord(
            firm_id=firm.id,
            product_id=product.id,
            batch_number=batch_number,
            expiry_date=expiry,
            status="AVAILABLE",
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(batch)
        session.flush()
        inventory.record_goods_receipt(
            firm_scope=firm.id,
            actor_id=actor_id,
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            storage_node_id=None,
            product_id=product.id,
            reference_number=f"GRN-{batch_number}",
            transaction_date=date(2026, 8, 3),
            total_quantity=Decimal(quantity),
            # Costless, so the dispatch does not also need the firm's control
            # accounts configured; this test is about which rows the stock
            # comes off, not about what it is worth.
            unit_cost=Decimal("0"),
            batch_id=batch.id,
        )
    session.commit()

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
                    quantity=Decimal("45"),
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
    # The order line reports the stock behind it, and that is a sum too.
    assert source_line.available_stock == Decimal("100.0000")

    service = DeliveryNoteService(session)
    note = service.create_note(
        DeliveryNoteCreate(
            sales_order_id=approved_order.id,
            delivery_date=date(2026, 8, 4),
            lines=[
                DeliveryNoteLineWrite(
                    sales_order_line_id=source_line.id,
                    line_number=1,
                    current_delivery_quantity=Decimal("45"),
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    approved_note = service.approve_note(note.id, firm_scope=firm.id, actor_id=actor_id)
    dispatched = service.dispatch_note(
        approved_note.id, firm_scope=firm.id, actor_id=actor_id
    )

    assert dispatched.status == DeliveryNoteStatus.DISPATCHED.value
    movements = list(
        session.scalars(
            select(InventoryTransaction).where(
                InventoryTransaction.transaction_type == "DISPATCH",
                InventoryTransaction.reference_number
                == dispatched.delivery_note_number,
            )
        ).all()
    )
    assert len(movements) == 2, "one movement per batch drawn from"
    assert sum(row.current_quantity_delta for row in movements) == Decimal("-45.0000")


def test_a_reservation_holds_the_batch_it_will_ship_from() -> None:
    """Committing stock commits particular stock, not just the product.

    The reservation used to go to the untracked row whatever the goods were
    held in, so a firm whose stock is all in batches had reservations against a
    row with nothing in it -- its available driven negative while the batch
    rows sat apparently free, ready to be promised to somebody else.

    Dispatch then releases and immediately draws, both ranking by earliest
    expiry, so the batch freed is the batch shipped.
    """
    session_factory = _session_factory()
    session = session_factory()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    customer = _customer(session, firm_id=firm.id)
    product = _product(session, firm_id=firm.id)
    actor_id = uuid4()

    inventory = InventoryService(session)
    batches: dict[str, BatchRecord] = {}
    for batch_number, expiry, quantity in (
        ("MARCH", date(2027, 3, 31), "20"),
        ("JUNE", date(2027, 6, 30), "20"),
    ):
        batch = BatchRecord(
            firm_id=firm.id,
            product_id=product.id,
            batch_number=batch_number,
            expiry_date=expiry,
            status="AVAILABLE",
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(batch)
        session.flush()
        batches[batch_number] = batch
        inventory.record_goods_receipt(
            firm_scope=firm.id,
            actor_id=actor_id,
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            storage_node_id=None,
            product_id=product.id,
            reference_number=f"GRN-{batch_number}",
            transaction_date=date(2026, 8, 3),
            total_quantity=Decimal(quantity),
            unit_cost=Decimal("0"),
            batch_id=batch.id,
        )
    session.commit()

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
                    quantity=Decimal("15"),
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

    reserved = list(
        session.scalars(
            select(InventoryTransaction).where(
                InventoryTransaction.transaction_type == "RESERVE",
                InventoryTransaction.reference_number == approved.order_number,
            )
        ).all()
    )
    assert len(reserved) == 1, "fifteen fits in the March batch alone"
    assert (
        reserved[0].batch_id == batches["MARCH"].id
    ), "the earliest expiry is held first, which is what will ship first"
    march_row = session.scalar(
        select(InventoryRecord).where(InventoryRecord.batch_id == batches["MARCH"].id)
    )
    assert march_row is not None
    assert march_row.reserved_quantity == Decimal("15.0000")
    assert march_row.available_quantity == Decimal("5.0000")
    untracked = session.scalar(
        select(InventoryRecord).where(
            InventoryRecord.product_id == product.id,
            InventoryRecord.batch_id.is_(None),
        )
    )
    assert untracked is None, "nothing was reserved against stock that is not there"


def test_a_reservation_larger_than_the_stock_holds_what_it_can() -> None:
    """An order may be taken for more than is on the shelf.

    That is a back order and the reports count on it, so a reservation must
    not fail for want of stock. The batches hold what they can and the rest is
    held with no batch, because there is no batch behind it.
    """
    session_factory = _session_factory()
    session = session_factory()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    customer = _customer(session, firm_id=firm.id)
    product = _product(session, firm_id=firm.id)
    actor_id = uuid4()

    batch = BatchRecord(
        firm_id=firm.id,
        product_id=product.id,
        batch_number="MARCH",
        expiry_date=date(2027, 3, 31),
        status="AVAILABLE",
        created_by=actor_id,
        updated_by=actor_id,
    )
    session.add(batch)
    session.flush()
    InventoryService(session).record_goods_receipt(
        firm_scope=firm.id,
        actor_id=actor_id,
        branch_id=branch.id,
        warehouse_id=warehouse.id,
        storage_node_id=None,
        product_id=product.id,
        reference_number="GRN-MARCH",
        transaction_date=date(2026, 8, 3),
        total_quantity=Decimal("10"),
        unit_cost=Decimal("0"),
        batch_id=batch.id,
    )
    session.commit()

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
                    quantity=Decimal("25"),
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

    reserved = list(
        session.scalars(
            select(InventoryTransaction).where(
                InventoryTransaction.transaction_type == "RESERVE",
                InventoryTransaction.reference_number == approved.order_number,
            )
        ).all()
    )
    held = {row.batch_id: row.reserved_quantity_delta for row in reserved}
    assert held[batch.id] == Decimal("10.0000"), "the batch holds all it has"
    assert held[None] == Decimal("15.0000"), "the back order is held by no batch"


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


def test_the_customers_standing_discount_reaches_a_delivery_note() -> None:
    """A dispatch prices itself the way the order it delivers was priced."""
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    customer = _customer(session, firm_id=firm.id)
    customer.default_discount_percent = Decimal("10")
    session.commit()
    product = _product(session, firm_id=firm.id)
    actor_id = uuid4()

    InventoryService(session).create_adjustment(
        InventoryAdjustmentCreate(
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            product_id=product.id,
            quantity=Decimal("10"),
            reference_number="ADJ-D1",
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
    assert response.line_discount_total == Decimal("40.0000")
    assert response.grand_total == Decimal("360.0000")
    assert response.customer_discount_percent == Decimal("10.0000")


def _stock(
    session: Session,
    *,
    firm: Firm,
    branch: Branch,
    warehouse: Warehouse,
    product: Product,
    quantity: Decimal = Decimal("100"),
) -> None:
    """Put enough on the shelf that dispatch is not the thing under test."""
    InventoryService(session).create_adjustment(
        InventoryAdjustmentCreate(
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            product_id=product.id,
            quantity=quantity,
            reference_number="ADJ-STATUS",
            reference_type="ADJUSTMENT",
            transaction_date=date(2026, 8, 3),
        ),
        firm_scope=firm.id,
        actor_id=uuid4(),
    )


def _approved_order(
    session: Session,
    *,
    firm: Firm,
    branch: Branch,
    warehouse: Warehouse,
    customer: Customer,
    product: Product,
    quantity: Decimal,
    actor_id: UUID,
) -> tuple[SalesOrder, SalesOrderLine]:
    """Raise and approve an order, and return it with its only line."""
    orders = SalesOrderService(session)
    order = orders.create_order(
        SalesOrderCreate(
            customer_id=customer.id,
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            order_date=date(2026, 8, 3),
            lines=[
                SalesOrderLineWrite(
                    line_number=1,
                    product_id=product.id,
                    quantity=quantity,
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    orders.approve_order(order.id, firm_scope=firm.id, actor_id=actor_id)
    line = session.scalar(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order.id)
    )
    assert line is not None
    return order, line


def _dispatch(
    session: Session,
    *,
    firm: Firm,
    order: SalesOrder,
    order_line: SalesOrderLine,
    quantity: Decimal,
    on: date,
    actor_id: UUID,
) -> DeliveryNote:
    """Raise, approve and dispatch one note against the order."""
    service = DeliveryNoteService(session)
    note = service.create_note(
        DeliveryNoteCreate(
            sales_order_id=order.id,
            delivery_date=on,
            lines=[
                DeliveryNoteLineWrite(
                    sales_order_line_id=order_line.id,
                    line_number=1,
                    current_delivery_quantity=quantity,
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    service.approve_note(note.id, firm_scope=firm.id, actor_id=actor_id)
    return service.dispatch_note(note.id, firm_scope=firm.id, actor_id=actor_id)


def test_dispatching_part_of_an_order_moves_it_to_partially_delivered() -> None:
    """Nothing wrote these statuses until 2026-08-23.

    A fully delivered order and one nothing had shipped against both read
    APPROVED, so every screen had to work out "is this finished?" from the
    notes. The purchase side has had the same pair since 2026-08-18.
    """
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    customer = _customer(session, firm_id=firm.id)
    product = _product(session, firm_id=firm.id)
    actor_id = uuid4()
    _stock(session, firm=firm, branch=branch, warehouse=warehouse, product=product)

    order, order_line = _approved_order(
        session,
        firm=firm,
        branch=branch,
        warehouse=warehouse,
        customer=customer,
        product=product,
        quantity=Decimal("10"),
        actor_id=actor_id,
    )
    _dispatch(
        session,
        firm=firm,
        order=order,
        order_line=order_line,
        quantity=Decimal("4"),
        on=date(2026, 8, 4),
        actor_id=actor_id,
    )

    session.refresh(order)
    assert order.status == SalesOrderStatus.PARTIALLY_DELIVERED.value


def test_dispatching_the_rest_moves_it_to_delivered() -> None:
    """Derived by summing the notes, not by incrementing a counter."""
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    customer = _customer(session, firm_id=firm.id)
    product = _product(session, firm_id=firm.id)
    actor_id = uuid4()
    _stock(session, firm=firm, branch=branch, warehouse=warehouse, product=product)

    order, order_line = _approved_order(
        session,
        firm=firm,
        branch=branch,
        warehouse=warehouse,
        customer=customer,
        product=product,
        quantity=Decimal("10"),
        actor_id=actor_id,
    )
    for sent, day in ((Decimal("4"), 4), (Decimal("6"), 5)):
        _dispatch(
            session,
            firm=firm,
            order=order,
            order_line=order_line,
            quantity=sent,
            on=date(2026, 8, day),
            actor_id=actor_id,
        )

    session.refresh(order)
    assert order.status == SalesOrderStatus.DELIVERED.value


def test_a_second_note_can_still_be_raised_once_the_order_has_moved() -> None:
    """The gate that would have broken.

    It compared the **sales order's** status against `DeliveryNoteStatus`
    members, which agreed only because both enums spell APPROVED and CLOSED
    the same. Writing PARTIALLY_DELIVERED would have made it refuse every
    second delivery -- a part-shipped order could never be completed.
    """
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    customer = _customer(session, firm_id=firm.id)
    product = _product(session, firm_id=firm.id)
    actor_id = uuid4()
    _stock(session, firm=firm, branch=branch, warehouse=warehouse, product=product)

    order, order_line = _approved_order(
        session,
        firm=firm,
        branch=branch,
        warehouse=warehouse,
        customer=customer,
        product=product,
        quantity=Decimal("10"),
        actor_id=actor_id,
    )
    _dispatch(
        session,
        firm=firm,
        order=order,
        order_line=order_line,
        quantity=Decimal("4"),
        on=date(2026, 8, 4),
        actor_id=actor_id,
    )
    session.refresh(order)
    assert order.status == SalesOrderStatus.PARTIALLY_DELIVERED.value

    # The one that used to be refused.
    second = _dispatch(
        session,
        firm=firm,
        order=order,
        order_line=order_line,
        quantity=Decimal("2"),
        on=date(2026, 8, 5),
        actor_id=actor_id,
    )

    assert second.status == DeliveryNoteStatus.DISPATCHED.value


def test_an_undispatched_note_leaves_the_order_where_it_is() -> None:
    """Stock moves at dispatch, so an approved note has delivered nothing."""
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    customer = _customer(session, firm_id=firm.id)
    product = _product(session, firm_id=firm.id)
    actor_id = uuid4()
    _stock(session, firm=firm, branch=branch, warehouse=warehouse, product=product)

    order, order_line = _approved_order(
        session,
        firm=firm,
        branch=branch,
        warehouse=warehouse,
        customer=customer,
        product=product,
        quantity=Decimal("10"),
        actor_id=actor_id,
    )
    service = DeliveryNoteService(session)
    note = service.create_note(
        DeliveryNoteCreate(
            sales_order_id=order.id,
            delivery_date=date(2026, 8, 4),
            lines=[
                DeliveryNoteLineWrite(
                    sales_order_line_id=order_line.id,
                    line_number=1,
                    current_delivery_quantity=Decimal("4"),
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    service.approve_note(note.id, firm_scope=firm.id, actor_id=actor_id)

    session.refresh(order)
    assert order.status == SalesOrderStatus.APPROVED.value
