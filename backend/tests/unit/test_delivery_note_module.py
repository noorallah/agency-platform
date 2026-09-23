"""Delivery note backend lifecycle and inventory-dispatch tests."""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.batch_serial.models import batch_serial as _batch_serial_models  # noqa: F401
from app.batch_serial.models.batch_serial import BatchRecord
from app.branches.models import Branch, Warehouse
from app.business.models import BusinessFeature, BusinessProfile, ProfileFeature
from app.business.models import framework as _business_models  # noqa: F401
from app.common.audit.models import AuditLog
from app.core.database.base import Base
from app.core.exceptions import AuthorizationError, ValidationError
from app.customers.models import Customer
from app.delivery_note.models import DeliveryNote, DeliveryNoteLine
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
from app.sales.models import (
    SalesTerritoryNode,
    TerritoryCustomerAssignment,
    TerritoryRouteProfile,
)
from app.sales.models import territory as _sales_models  # noqa: F401
from app.sales_invoice.models import SalesInvoiceLine
from app.sales_invoice.schemas import (
    SalesInvoiceCreate,
    SalesInvoiceLineWrite,
    SalesInvoiceSourceType,
)
from app.sales_invoice.services import SalesInvoiceService
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
    # Named, so a picker of notes says whose each one is (plan item 9.22).
    assert response.customer_name == "Customer CUS-001"
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


def _stale_and_fresh_order(
    order_date: date, quantity: str
) -> tuple[Session, UUID, UUID, dict[str, BatchRecord], SalesOrder]:
    """Stock ten of a batch expired on 2026-08-17 and ten in date; approve.

    Returns the session, the firm and actor, the two batches by name, and the
    order approved for ``quantity`` on ``order_date``.
    """
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    customer = _customer(session, firm_id=firm.id)
    product = _product(session, firm_id=firm.id)
    actor_id = uuid4()

    inventory = InventoryService(session)
    batches: dict[str, BatchRecord] = {}
    for batch_number, expiry in (
        ("STALE", date(2026, 8, 17)),
        ("FRESH", date(2027, 10, 21)),
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
            order_date=order_date,
            lines=[
                SalesOrderLineWrite(
                    line_number=1,
                    product_id=product.id,
                    quantity=Decimal(quantity),
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
    return session, firm.id, actor_id, batches, approved


def _movements(
    session: Session, transaction_type: str, reference_number: str
) -> list[InventoryTransaction]:
    """Return the movements of one type posted under one reference."""
    return list(
        session.scalars(
            select(InventoryTransaction).where(
                InventoryTransaction.transaction_type == transaction_type,
                InventoryTransaction.reference_number == reference_number,
            )
        ).all()
    )


def test_a_reservation_skips_a_batch_that_has_expired() -> None:
    """The hold goes on the stock that will ship, not on stock that cannot.

    Dispatch stopped drawing expired batches (D-8-1) while reservation went on
    holding them, earliest expiry read literally: a pharmacy approving an
    order for five held the batch that expired in August, the note then
    shipped from the in-date batch, and that batch had stayed free for anybody
    else to promise the whole time (D-STK-2). Reserve and dispatch now drop
    the same stock, so the batch released is the batch drawn.
    """
    session, firm_id, actor_id, batches, order = _stale_and_fresh_order(
        date(2026, 9, 16), "5"
    )

    reserved = _movements(session, "RESERVE", order.order_number)
    assert [(row.batch_id, row.reserved_quantity_delta) for row in reserved] == [
        (batches["FRESH"].id, Decimal("5.0000"))
    ], "expired stock is not a candidate for a hold"
    stale_row = session.scalar(
        select(InventoryRecord).where(InventoryRecord.batch_id == batches["STALE"].id)
    )
    assert stale_row is not None
    assert stale_row.reserved_quantity == Decimal("0.0000")

    source_line = session.scalar(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order.id)
    )
    assert source_line is not None
    service = DeliveryNoteService(session)
    note = service.create_note(
        DeliveryNoteCreate(
            sales_order_id=order.id,
            delivery_date=date(2026, 9, 17),
            lines=[
                DeliveryNoteLineWrite(
                    sales_order_line_id=source_line.id,
                    line_number=1,
                    current_delivery_quantity=Decimal("5"),
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=firm_id,
        actor_id=actor_id,
    )
    approved_note = service.approve_note(note.id, firm_scope=firm_id, actor_id=actor_id)
    service.dispatch_note(approved_note.id, firm_scope=firm_id, actor_id=actor_id)

    released = _movements(session, "UNRESERVE", order.order_number)
    dispatched = _movements(session, "DISPATCH", note.delivery_note_number)
    assert {row.batch_id for row in released} == {batches["FRESH"].id}
    assert {row.batch_id for row in dispatched} == {
        batches["FRESH"].id
    }, "the batch let go is the batch shipped"


def test_a_back_order_behind_expired_stock_names_the_batch() -> None:
    """Twenty on the shelf and five back-ordered needs saying why, by name.

    The ten in date are held; the other five have no batch behind them,
    because the only other stock went out of date on 2026-08-17. The hold on
    no batch carries the same words dispatch refuses with.
    """
    session, _firm_id, _actor_id, batches, order = _stale_and_fresh_order(
        date(2026, 9, 16), "15"
    )

    reserved = _movements(session, "RESERVE", order.order_number)
    held = {row.batch_id: row for row in reserved}
    assert set(held) == {batches["FRESH"].id, None}
    assert held[batches["FRESH"].id].reserved_quantity_delta == Decimal("10.0000")
    back_order = held[None]
    assert back_order.reserved_quantity_delta == Decimal("5.0000")
    assert back_order.remarks is not None
    assert "STALE expired 2026-08-17" in back_order.remarks
    assert "cannot be reserved" in back_order.remarks
    assert held[batches["FRESH"].id].remarks == "sales_order reserve line 1"


def test_a_reservation_judges_expiry_on_the_orders_own_date() -> None:
    """An order dated while the batch was good holds it, for ever.

    The demo history is rebuilt from the services long after the fact, so
    reading the clock rather than the order would move a replayed hold -- the
    same rule dispatch follows with the note's date.
    """
    session, _firm_id, _actor_id, batches, order = _stale_and_fresh_order(
        date(2026, 8, 16), "5"
    )

    reserved = _movements(session, "RESERVE", order.order_number)
    assert [row.batch_id for row in reserved] == [batches["STALE"].id]


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
    # A named route has to be one the customer is on (D-TER-9).
    session.add(
        TerritoryCustomerAssignment(
            territory_id=territory.id, customer_id=customer.id, is_primary=True
        )
    )
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
    # Only a dispatched note has delivered anything (D-RPT-9).
    service.approve_note(note.id, firm_scope=firm.id, actor_id=actor_id)
    service.dispatch_note(note.id, firm_scope=firm.id, actor_id=actor_id)

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


def test_a_note_cannot_ship_more_than_the_order() -> None:
    """Delivery is capped at the order line, with no tolerance."""
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
        quantity=Decimal("10"),
        on=date(2026, 8, 4),
        actor_id=actor_id,
    )

    with pytest.raises(ValidationError, match="exceeds allowed quantity"):
        _dispatch(
            session,
            firm=firm,
            order=order,
            order_line=order_line,
            quantity=Decimal("1"),
            on=date(2026, 8, 5),
            actor_id=actor_id,
        )


def test_a_note_cannot_lift_its_own_cap() -> None:
    """D-SELL-31: the request body used to carry a switch for the cap.

    Driven 2026-09-19 on ``fx_t0919q38d_s``: a third note for 30 against an
    order for 12 already shipped in full, with ``allow_over_delivery`` true and
    ``over_delivery_percent`` 500 -- approved and dispatched, 42 out of the
    warehouse against 12 ordered. The write schema no longer takes either
    field; a tolerance, if a firm wants one, is the firm's to set.
    """
    body = DeliveryNoteCreate(
        sales_order_id=uuid4(),
        delivery_date=date(2026, 8, 4),
        lines=[
            DeliveryNoteLineWrite(
                sales_order_line_id=uuid4(),
                line_number=1,
                current_delivery_quantity=Decimal("30"),
            )
        ],
    ).model_dump(mode="json")

    for field, value in (
        ("allow_over_delivery", True),
        ("over_delivery_percent", 500),
    ):
        with pytest.raises(PydanticValidationError, match=field):
            DeliveryNoteCreate.model_validate({**body, field: value})


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


def _approved_note(
    session: Session,
    *,
    firm: Firm,
    order: SalesOrder,
    order_line: SalesOrderLine,
    quantity: Decimal,
    actor_id: UUID,
) -> DeliveryNote:
    """Raise and approve one note against the order, without dispatching it."""
    service = DeliveryNoteService(session)
    note = service.create_note(
        DeliveryNoteCreate(
            sales_order_id=order.id,
            delivery_date=date(2026, 8, 4),
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
    return service.approve_note(note.id, firm_scope=firm.id, actor_id=actor_id)


def test_an_approved_note_that_never_dispatched_cannot_be_closed() -> None:
    """A closed note reads as delivered, so only one whose goods left may close.

    D-SELL-4, driven 2026-09-19: an APPROVED note for 5 was closed, a second
    for 7 was dispatched, and the order of 12 read DELIVERED with 7 shipped --
    the closed note offered for billing and its 5 still reserved.
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
    note = _approved_note(
        session,
        firm=firm,
        order=order,
        order_line=order_line,
        quantity=Decimal("4"),
        actor_id=actor_id,
    )
    service = DeliveryNoteService(session)

    with pytest.raises(
        ValidationError, match="Only dispatched or completed delivery notes"
    ):
        service.close_note(note.id, firm_scope=firm.id, actor_id=actor_id)
    session.rollback()
    session.refresh(note)
    assert note.status == DeliveryNoteStatus.APPROVED.value

    # Once it has shipped, closing is what it always was.
    service.dispatch_note(note.id, firm_scope=firm.id, actor_id=actor_id)
    closed = service.close_note(note.id, firm_scope=firm.id, actor_id=actor_id)
    assert closed.status == DeliveryNoteStatus.CLOSED.value


def test_a_note_closed_without_dispatching_delivers_nothing() -> None:
    """A note closed before the refusal must not count as goods that left.

    Such rows exist, so the reads judge the goods, not the status: the order
    is not moved to DELIVERED by it and the bill screen does not offer it.
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
    stale = _approved_note(
        session,
        firm=firm,
        order=order,
        order_line=order_line,
        quantity=Decimal("4"),
        actor_id=actor_id,
    )
    # What `close_note` wrote before it refused an undispatched note.
    stale.status = DeliveryNoteStatus.CLOSED.value
    session.commit()

    shipped = _dispatch(
        session,
        firm=firm,
        order=order,
        order_line=order_line,
        quantity=Decimal("6"),
        on=date(2026, 8, 5),
        actor_id=actor_id,
    )

    session.refresh(order)
    assert order.status == SalesOrderStatus.PARTIALLY_DELIVERED.value
    offered = SalesInvoiceService(session).billable_documents(
        firm_scope=firm.id, limit=50
    )
    assert [row.source_document_id for row in offered] == [shipped.id]


def test_a_note_ships_the_deal_the_order_struck() -> None:
    """The rate on the order is the rate the goods leave under.

    A delivery note re-read the customer's *current* standing rate instead of
    inheriting the order line it ships, and the invoice then inherits from the
    note -- so a price agreed in March was quietly replaced by whatever the
    customer master said in August, which is the exact thing the invoice's own
    inheritance rule exists to prevent.

    It also silently discarded every promotion: an offer is applied when the
    order is priced, and the note threw the result away before the bill could
    inherit it.
    """
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    customer = _customer(session, firm_id=firm.id)
    product = _product(session, firm_id=firm.id)
    actor_id = uuid4()
    _stock(session, firm=firm, branch=branch, warehouse=warehouse, product=product)

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
                    quantity=Decimal("10"),
                    unit_price=Decimal("100"),
                    discount_percent=Decimal("12"),
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    orders.approve_order(order.id, firm_scope=firm.id, actor_id=actor_id)
    order_line = session.scalar(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order.id)
    )
    assert order_line is not None
    assert order_line.discount_percent == Decimal("12.0000")

    # The customer's standing rate changes after the order is placed. It must
    # not reach goods already agreed at another price.
    customer.default_discount_percent = Decimal("25")
    session.commit()

    note = _dispatch(
        session,
        firm=firm,
        order=order,
        order_line=order_line,
        quantity=Decimal("10"),
        on=date(2026, 8, 4),
        actor_id=actor_id,
    )

    line = session.scalar(
        select(DeliveryNoteLine).where(DeliveryNoteLine.delivery_note_id == note.id)
    )
    assert line is not None
    assert line.discount_percent == Decimal("12.0000"), (
        "the note ships what the order agreed, not what the customer master "
        "says today"
    )
    assert line.discount_amount == Decimal("120.0000")


def test_an_inherited_amount_is_pro_rated_across_a_part_shipment() -> None:
    """Half the order shipped carries half the discount it was given.

    A rate needs no such handling and is inherited as itself; a whole-line
    amount copied onto part of a line would discount more than was agreed.
    """
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    customer = _customer(session, firm_id=firm.id)
    product = _product(session, firm_id=firm.id)
    actor_id = uuid4()
    _stock(session, firm=firm, branch=branch, warehouse=warehouse, product=product)

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
                    quantity=Decimal("10"),
                    unit_price=Decimal("100"),
                    discount_amount=Decimal("200"),
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    orders.approve_order(order.id, firm_scope=firm.id, actor_id=actor_id)
    order_line = session.scalar(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order.id)
    )
    assert order_line is not None

    note = _dispatch(
        session,
        firm=firm,
        order=order,
        order_line=order_line,
        quantity=Decimal("5"),
        on=date(2026, 8, 4),
        actor_id=actor_id,
    )

    line = session.scalar(
        select(DeliveryNoteLine).where(DeliveryNoteLine.delivery_note_id == note.id)
    )
    assert line is not None
    assert line.discount_amount == Decimal("100.0000")


def test_a_note_may_still_be_given_a_discount_of_its_own() -> None:
    """What was asked for wins over what was inherited, as everywhere else."""
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    customer = _customer(session, firm_id=firm.id)
    product = _product(session, firm_id=firm.id)
    actor_id = uuid4()
    _stock(session, firm=firm, branch=branch, warehouse=warehouse, product=product)

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
                    quantity=Decimal("10"),
                    unit_price=Decimal("100"),
                    discount_percent=Decimal("12"),
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    orders.approve_order(order.id, firm_scope=firm.id, actor_id=actor_id)
    order_line = session.scalar(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order.id)
    )
    assert order_line is not None

    service = DeliveryNoteService(session)
    note = service.create_note(
        DeliveryNoteCreate(
            sales_order_id=order.id,
            delivery_date=date(2026, 8, 4),
            lines=[
                DeliveryNoteLineWrite(
                    sales_order_line_id=order_line.id,
                    line_number=1,
                    current_delivery_quantity=Decimal("10"),
                    unit_price=Decimal("100"),
                    discount_percent=Decimal("20"),
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )

    line = session.scalar(
        select(DeliveryNoteLine).where(DeliveryNoteLine.delivery_note_id == note.id)
    )
    assert line is not None
    assert line.discount_percent == Decimal("20.0000")


def _note_priced(unit_price: "Decimal | None") -> "DeliveryNoteLine":
    """Dispatch four of a line ordered at 100, saying this about the price."""
    session = _session_factory()()
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
            reference_number="ADJ-PRICE",
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
    note = DeliveryNoteService(session).create_note(
        DeliveryNoteCreate(
            sales_order_id=approved.id,
            delivery_date=date(2026, 8, 4),
            lines=[
                DeliveryNoteLineWrite(
                    sales_order_line_id=source_line.id,
                    line_number=1,
                    current_delivery_quantity=Decimal("4"),
                    unit_price=unit_price,
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    session.commit()
    line = session.scalar(
        select(DeliveryNoteLine).where(DeliveryNoteLine.delivery_note_id == note.id)
    )
    assert line is not None
    return line


def test_a_note_ships_at_the_price_the_order_struck() -> None:
    """Silence means "whatever was agreed", not "nothing".

    The discount already inherited this way -- a note ships the deal the order
    struck -- and the price did not: it defaulted to zero, so a caller that
    omitted it dispatched at no price at all and every document downstream
    inherited the nothing. A note valued at zero against goods that left the
    warehouse is the quietest way this module could fail.
    """
    line = _note_priced(None)

    assert line.unit_price == Decimal("100.0000")
    assert line.gross_amount == Decimal("400.0000")


def test_a_note_can_still_ship_at_a_price_of_its_own() -> None:
    """What was asked for beats what was assumed, here as everywhere.

    And zero is asking: goods dispatched at no charge are a real thing, and a
    different statement from saying nothing at all.
    """
    line = _note_priced(Decimal("0"))

    assert line.unit_price == Decimal("0.0000")
    assert line.gross_amount == Decimal("0.0000")


def test_dispatch_from_another_warehouse_releases_where_the_order_reserved() -> None:
    """The reservation is let go where it was made, not where goods leave.

    An order reserved in the north warehouse and shipped from the depot
    released its reservation from the depot -- the note line's warehouse --
    so the north warehouse kept a hold on stock nobody would ever ship, and
    the depot's reserved quantity went down for an order it never held
    (plan item 9.12, 2026-09-13).
    """
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    north = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    depot = Warehouse(
        firm_id=firm.id,
        branch_id=branch.id,
        code="WH-DEPOT",
        name="Depot",
        display_name="Depot",
        status="ACTIVE",
    )
    session.add(depot)
    session.commit()
    customer = _customer(session, firm_id=firm.id)
    product = _product(session, firm_id=firm.id)
    actor_id = uuid4()
    _stock(session, firm=firm, branch=branch, warehouse=north, product=product)
    _stock(session, firm=firm, branch=branch, warehouse=depot, product=product)

    order, order_line = _approved_order(
        session,
        firm=firm,
        branch=branch,
        warehouse=north,
        customer=customer,
        product=product,
        quantity=Decimal("12"),
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
                    current_delivery_quantity=Decimal("5"),
                    unit_price=Decimal("100"),
                    warehouse_id=depot.id,
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    service.approve_note(note.id, firm_scope=firm.id, actor_id=actor_id)
    service.dispatch_note(note.id, firm_scope=firm.id, actor_id=actor_id)

    def _held(warehouse: Warehouse) -> tuple[Decimal, Decimal]:
        rows = session.scalars(
            select(InventoryRecord).where(
                InventoryRecord.warehouse_id == warehouse.id,
                InventoryRecord.product_id == product.id,
            )
        ).all()
        return (
            sum((Decimal(str(r.current_quantity)) for r in rows), Decimal("0")),
            sum((Decimal(str(r.reserved_quantity)) for r in rows), Decimal("0")),
        )

    assert _held(north) == (Decimal("100"), Decimal("7"))
    assert _held(depot) == (Decimal("95"), Decimal("0"))


def test_closing_a_part_shipped_order_gives_back_the_rest_of_its_hold() -> None:
    """Closing (or cancelling) released stock only for an APPROVED order.

    Closing is the only way to end a part-shipped order now: cancelling one
    that a note has shipped is refused (D-SELL-11).

    Once a note ships part of it the order reads PARTIALLY_DELIVERED, and
    both actions checked for APPROVED alone -- so the undelivered remainder
    stayed reserved for ever. Releasing it then over-released, because the
    movement was converted from the whole line's entered quantity rather
    than the share still held (found beside plan item 9.9, 2026-09-13).
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

    SalesOrderService(session).close_order(
        order.id, firm_scope=firm.id, actor_id=actor_id, reason="customer gone"
    )

    records = session.scalars(
        select(InventoryRecord).where(
            InventoryRecord.warehouse_id == warehouse.id,
            InventoryRecord.product_id == product.id,
        )
    ).all()
    assert sum(
        (Decimal(str(row.reserved_quantity)) for row in records), Decimal("0")
    ) == Decimal("0")
    assert sum(
        (Decimal(str(row.current_quantity)) for row in records), Decimal("0")
    ) == Decimal("96")
    session.refresh(order_line)
    assert order_line.reserved_quantity == Decimal("0")


def _order_with_a_shipment(
    session: Session,
) -> tuple[Firm, SalesOrder, SalesOrderLine, UUID]:
    """Return a firm and its order for 10, of which a note has shipped 4."""
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
    return firm, order, order_line, actor_id


def test_an_order_that_has_shipped_cannot_be_cancelled() -> None:
    """D-SELL-11: the goods had left and the order read CANCELLED.

    Driven 2026-09-19 on ``fx_t09194xes_s``: SO-2026-2027-000001, DELIVERED
    by two dispatched notes, was cancelled with a 200, which also handed its
    offer claims back while the discount stood on the bill. Closing is the
    way to end an order part of which has happened.
    """
    session = _session_factory()()
    firm, order, _, actor_id = _order_with_a_shipment(session)

    with pytest.raises(ValidationError, match="cannot be cancelled while"):
        SalesOrderService(session).cancel_order(
            order.id, firm_scope=firm.id, actor_id=actor_id, reason="too late"
        )
    session.rollback()
    session.refresh(order)
    assert order.status == SalesOrderStatus.PARTIALLY_DELIVERED.value


def test_a_closed_order_takes_no_further_note() -> None:
    """D-SELL-11: a note was accepted against a CLOSED order.

    Closing released the reservation for the undelivered 6, and a new note
    for them could still be raised, approved and shipped.
    """
    session = _session_factory()()
    firm, order, order_line, actor_id = _order_with_a_shipment(session)
    SalesOrderService(session).close_order(
        order.id, firm_scope=firm.id, actor_id=actor_id, reason="customer gone"
    )

    with pytest.raises(ValidationError, match="is CLOSED"):
        DeliveryNoteService(session).create_note(
            DeliveryNoteCreate(
                sales_order_id=order.id,
                delivery_date=date(2026, 8, 5),
                lines=[
                    DeliveryNoteLineWrite(
                        sales_order_line_id=order_line.id,
                        line_number=1,
                        current_delivery_quantity=Decimal("2"),
                        unit_price=Decimal("100"),
                    )
                ],
            ),
            firm_id=firm.id,
            actor_id=actor_id,
        )


def test_a_note_approved_before_the_close_does_not_ship() -> None:
    """Only create asked, so a note already approved still went out."""
    session = _session_factory()()
    firm, order, order_line, actor_id = _order_with_a_shipment(session)
    service = DeliveryNoteService(session)
    note = service.create_note(
        DeliveryNoteCreate(
            sales_order_id=order.id,
            delivery_date=date(2026, 8, 5),
            lines=[
                DeliveryNoteLineWrite(
                    sales_order_line_id=order_line.id,
                    line_number=1,
                    current_delivery_quantity=Decimal("2"),
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    service.approve_note(note.id, firm_scope=firm.id, actor_id=actor_id)
    SalesOrderService(session).close_order(
        order.id, firm_scope=firm.id, actor_id=actor_id, reason="customer gone"
    )

    with pytest.raises(ValidationError, match="is CLOSED"):
        service.dispatch_note(note.id, firm_scope=firm.id, actor_id=actor_id)
    session.rollback()
    with pytest.raises(ValidationError, match="is CLOSED"):
        service.complete_note(note.id, firm_scope=firm.id, actor_id=actor_id)


def test_dispatch_from_another_branchs_warehouse_finds_its_stock() -> None:
    """Stock is looked for at the branch the warehouse belongs to.

    A note takes its branch from the order. Shipping a North order from the
    head office's depot looked for stock at North's branch paired with the
    depot -- a location holding nothing -- and was refused, "Insufficient
    available stock for dispatch line.", with 785 on the depot's shelf (plan
    item 9.12, 2026-09-13). The transfer screen had the same shape in 8.3.
    """
    session = _session_factory()()
    firm = _firm(session)
    north = _branch(session, firm_id=firm.id)
    head_office = Branch(
        firm_id=firm.id,
        code="BR-HO",
        name="Head Office",
        display_name="Head Office",
        status="ACTIVE",
    )
    session.add(head_office)
    session.commit()
    north_wh = _warehouse(session, firm_id=firm.id, branch_id=north.id)
    depot = Warehouse(
        firm_id=firm.id,
        branch_id=head_office.id,
        code="WH-DEPOT",
        name="Depot",
        display_name="Depot",
        status="ACTIVE",
    )
    session.add(depot)
    session.commit()
    customer = _customer(session, firm_id=firm.id)
    product = _product(session, firm_id=firm.id)
    actor_id = uuid4()
    _stock(session, firm=firm, branch=head_office, warehouse=depot, product=product)

    order, order_line = _approved_order(
        session,
        firm=firm,
        branch=north,
        warehouse=north_wh,
        customer=customer,
        product=product,
        quantity=Decimal("12"),
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
                    current_delivery_quantity=Decimal("5"),
                    unit_price=Decimal("100"),
                    warehouse_id=depot.id,
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    service.approve_note(note.id, firm_scope=firm.id, actor_id=actor_id)
    service.dispatch_note(note.id, firm_scope=firm.id, actor_id=actor_id)

    def _held(warehouse: Warehouse, branch: Branch) -> tuple[Decimal, Decimal]:
        rows = session.scalars(
            select(InventoryRecord).where(
                InventoryRecord.warehouse_id == warehouse.id,
                InventoryRecord.branch_id == branch.id,
                InventoryRecord.product_id == product.id,
            )
        ).all()
        return (
            sum((Decimal(str(r.current_quantity)) for r in rows), Decimal("0")),
            sum((Decimal(str(r.reserved_quantity)) for r in rows), Decimal("0")),
        )

    assert _held(depot, head_office) == (Decimal("95"), Decimal("0"))
    assert _held(north_wh, north) == (Decimal("0"), Decimal("7"))


def test_a_note_approved_before_the_hold_does_not_ship() -> None:
    """Neither dispatching it nor completing it, which dispatches it too.

    D-SELL-5, driven 2026-09-19: only a note's create asked about the hold, so
    notes approved before it were dispatched and completed while the order
    read "on hold", and the goods left.
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
    SalesOrderService(session).hold_order(
        order.id, reason="Awaiting cheque.", firm_scope=firm.id, actor_id=actor_id
    )

    for act in (service.dispatch_note, service.complete_note):
        with pytest.raises(ValidationError, match=r"on hold .*Awaiting cheque"):
            act(note.id, firm_scope=firm.id, actor_id=actor_id)
        session.rollback()

    session.refresh(note)
    assert note.status == DeliveryNoteStatus.APPROVED.value
    assert note.dispatched_at is None
    assert (
        session.scalar(
            select(InventoryTransaction).where(
                InventoryTransaction.transaction_type == "DISPATCH"
            )
        )
        is None
    )


def test_orders_not_yet_delivered_are_the_ones_still_owing_stock() -> None:
    """The report follows what left the warehouse, as the order's status does.

    It held DRAFT and APPROVED alone, so a PARTIALLY_DELIVERED order -- the one
    that most literally still owed stock -- was absent, an unapproved draft was
    in, and `pending_value` was the whole total whatever had gone (D-RPT-7:
    SO-2026-2027-000017, 4 of 10 dispatched, missing from the report).
    """
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    customer = _customer(session, firm_id=firm.id)
    product = _product(session, firm_id=firm.id)
    actor_id = uuid4()
    _stock(session, firm=firm, branch=branch, warehouse=warehouse, product=product)
    orders = SalesOrderService(session)

    draft = orders.create_order(
        SalesOrderCreate(
            customer_id=customer.id,
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            order_date=date(2026, 8, 3),
            lines=[
                SalesOrderLineWrite(
                    line_number=1,
                    product_id=product.id,
                    quantity=Decimal("3"),
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
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
    session.refresh(order)
    whole = order.grand_total

    [row] = orders.pending_orders(firm_scope=firm.id)
    assert row.order_id == order.id, "the draft reserves nothing and owes nothing"
    assert (row.ordered_quantity, row.pending_quantity) == (10, 10)
    assert row.pending_value == whole.quantize(Decimal("0.01"))
    assert row.customer_name == customer.display_name
    assert draft.status == SalesOrderStatus.DRAFT.value

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
    [row] = orders.pending_orders(firm_scope=firm.id)
    assert row.status == SalesOrderStatus.PARTIALLY_DELIVERED
    assert (row.delivered_quantity, row.pending_quantity) == (4, 6)
    assert row.pending_value == (whole * Decimal("0.6")).quantize(Decimal("0.01"))

    _dispatch(
        session,
        firm=firm,
        order=order,
        order_line=order_line,
        quantity=Decimal("6"),
        on=date(2026, 8, 5),
        actor_id=actor_id,
    )
    assert orders.pending_orders(firm_scope=firm.id) == []


def test_the_delivery_reports_count_what_left_the_warehouse() -> None:
    """A note has delivered nothing until it is dispatched.

    The by-route, by-salesman and by-warehouse reports summed every
    non-cancelled note, so a DRAFT's typed quantity raised the warehouse's
    delivered total; the progress report counted an APPROVED note as
    delivered, so an order whose note was approved and never dispatched read
    4 delivered, 6 pending while nothing had moved (D-RPT-9, driven on
    DN-TEST01-HO-2026-2027-000010).
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
    service = DeliveryNoteService(session)

    def warehouse_row() -> tuple[int, Decimal]:
        rows = service.by_warehouse_report(firm_scope=firm.id)
        mine = [row for row in rows if row.dimension_id == warehouse.id]
        if not mine:
            return (0, Decimal("0"))
        return (mine[0].note_count, mine[0].delivered_quantity)

    def progress() -> tuple[Decimal, Decimal, str]:
        [row] = [
            row
            for row in service.partially_delivered_orders(firm_scope=firm.id)
            if row.sales_order_id == order.id
        ]
        return row.delivered_quantity, row.pending_quantity, row.status

    note = _approved_note(
        session,
        firm=firm,
        order=order,
        order_line=order_line,
        quantity=Decimal("4"),
        actor_id=actor_id,
    )
    assert warehouse_row() == (0, Decimal("0")), "an approved note delivered nothing"
    assert progress() == (Decimal("0"), Decimal("10"), "PENDING")

    service.dispatch_note(note.id, firm_scope=firm.id, actor_id=actor_id)
    assert warehouse_row() == (1, Decimal("4.0000"))
    assert progress() == (Decimal("4.0000"), Decimal("6.0000"), "PARTIAL")


def test_the_by_dimension_reports_name_their_keys_in_one_read() -> None:
    """D-RPT-19: the route and warehouse labels cost one query per key.

    Only the salesperson names were batched; a route was looked up by joining
    its territory once per distinct route and a warehouse once per distinct
    warehouse, inside the row loop. The rows answered are the same either
    way, so only the statements the session runs can tell them apart.
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
        quantity=Decimal("4"),
        actor_id=actor_id,
    )
    service = DeliveryNoteService(session)
    note = _approved_note(
        session,
        firm=firm,
        order=order,
        order_line=order_line,
        quantity=Decimal("4"),
        actor_id=actor_id,
    )
    service.dispatch_note(note.id, firm_scope=firm.id, actor_id=actor_id)

    statements: list[str] = []

    def _record(
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,  # noqa: FBT001 - SQLAlchemy's own signature
    ) -> None:
        """Keep every statement the engine is handed."""
        statements.append(statement)

    event.listen(session.get_bind(), "before_cursor_execute", _record)
    [row] = service.by_warehouse_report(firm_scope=firm.id)

    assert (row.dimension_id, row.dimension_name) == (warehouse.id, warehouse.name)
    assert not [text for text in statements if "warehouses.id = " in text]
    assert len([text for text in statements if "warehouses.id IN " in text]) == 1
    # A note with no route falls in the bucket the sales-order reports now
    # share with these (D-RPT-19).
    [by_route] = service.by_route_report(firm_scope=firm.id)
    assert (by_route.dimension_id, by_route.dimension_name) == (None, "Unassigned")


def test_a_back_order_is_a_live_shortfall_on_an_open_order() -> None:
    """Judged on today's stock and the order's life, not on the day it was typed.

    The report joined lines of every status and compared the reservable
    quantity with the `available_stock` snapshot written at save, so a
    cancelled draft for 45 against 40 on hand stayed "5 short" for ever, and a
    receipt landing later changed nothing (D-RPT-8; WHOLE01's five rows sat on
    CLOSED, CANCELLED, DELIVERED and DRAFT orders).
    """
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    customer = _customer(session, firm_id=firm.id)
    product = _product(session, firm_id=firm.id)
    actor_id = uuid4()
    _stock(
        session,
        firm=firm,
        branch=branch,
        warehouse=warehouse,
        product=product,
        quantity=Decimal("50"),
    )
    orders = SalesOrderService(session)

    def shortfalls() -> list[tuple[str, Decimal, Decimal, Decimal]]:
        return [
            (
                row.order_number,
                row.reserved_quantity,
                row.available_stock,
                row.back_order_quantity,
            )
            for row in orders.back_orders(firm_scope=firm.id)
        ]

    # A draft reserves nothing and is not the warehouse's problem yet.
    orders.create_order(
        SalesOrderCreate(
            customer_id=customer.id,
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            order_date=date(2026, 8, 3),
            lines=[
                SalesOrderLineWrite(
                    line_number=1,
                    product_id=product.id,
                    quantity=Decimal("100"),
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    assert shortfalls() == []

    # An approved order for 60 against 50 on hand: ten short.
    order, _ = _approved_order(
        session,
        firm=firm,
        branch=branch,
        warehouse=warehouse,
        customer=customer,
        product=product,
        quantity=Decimal("60"),
        actor_id=actor_id,
    )
    assert shortfalls() == [
        (order.order_number, Decimal("60.0000"), Decimal("50.0000"), Decimal("10.0000"))
    ]

    # Stock arriving closes it without anybody touching the order.
    _stock(
        session,
        firm=firm,
        branch=branch,
        warehouse=warehouse,
        product=product,
        quantity=Decimal("20"),
    )
    assert shortfalls() == []

    # A second order for 40 against the 10 left once the first has taken its
    # 60: thirty short, and the first stays whole. Cancelling it makes it
    # nobody's shortfall, whatever the stock.
    second, _ = _approved_order(
        session,
        firm=firm,
        branch=branch,
        warehouse=warehouse,
        customer=customer,
        product=product,
        quantity=Decimal("40"),
        actor_id=actor_id,
    )
    assert shortfalls() == [
        (
            second.order_number,
            Decimal("40.0000"),
            Decimal("70.0000"),
            Decimal("30.0000"),
        )
    ]
    orders.cancel_order(
        second.id, firm_scope=firm.id, actor_id=actor_id, reason="D-RPT-8"
    )
    assert shortfalls() == []


def test_a_note_and_a_bill_inherit_the_orders_freight() -> None:
    """The delivery charge agreed on the order reaches the note and the bill.

    Neither inherited it: a note raised from an order with 100.00 of freight
    carried none, and the bill raised on the note none either, so the charge
    the customer agreed to was never billed (D-SELL-36). Inherited by the
    share shipped and then the share billed -- the rule every other inherited
    amount follows -- and an explicit 0 still waives it.
    """
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    customer = _customer(session, firm_id=firm.id)
    product = _product(session, firm_id=firm.id)
    actor_id = uuid4()
    _stock(session, firm=firm, branch=branch, warehouse=warehouse, product=product)

    orders = SalesOrderService(session)
    order = orders.create_order(
        SalesOrderCreate(
            customer_id=customer.id,
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            order_date=date(2026, 8, 3),
            freight_amount=Decimal("100"),
            lines=[
                SalesOrderLineWrite(
                    line_number=1,
                    product_id=product.id,
                    quantity=Decimal("10"),
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    orders.approve_order(order.id, firm_scope=firm.id, actor_id=actor_id)
    order_line = session.scalar(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order.id)
    )
    assert order_line is not None
    assert order_line.freight_amount == Decimal("100.0000")

    # Four of ten leave: 40.00 of the freight goes with them.
    note = _dispatch(
        session,
        firm=firm,
        order=order,
        order_line=order_line,
        quantity=Decimal("4"),
        on=date(2026, 8, 4),
        actor_id=actor_id,
    )
    assert note.freight_amount == Decimal("40.0000")
    note_line = session.scalar(
        select(DeliveryNoteLine).where(DeliveryNoteLine.delivery_note_id == note.id)
    )
    assert note_line is not None
    assert note_line.freight_amount == Decimal("40.0000")

    # Two of the four are billed: 20.00 of the note's freight is charged.
    invoices = SalesInvoiceService(session)
    invoice = invoices.create_invoice(
        SalesInvoiceCreate(
            customer_id=customer.id,
            branch_id=branch.id,
            invoice_date=date(2026, 8, 5),
            source_documents=[
                {
                    "source_document_type": SalesInvoiceSourceType.DELIVERY_NOTE,
                    "source_document_id": note.id,
                }
            ],
            lines=[
                SalesInvoiceLineWrite(
                    source_document_type=SalesInvoiceSourceType.DELIVERY_NOTE,
                    source_document_id=note.id,
                    source_document_line_id=note_line.id,
                    line_number=1,
                    current_invoice_quantity=Decimal("2"),
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    assert invoice.freight_amount == Decimal("20.0000")
    invoice_line = session.scalar(
        select(SalesInvoiceLine).where(SalesInvoiceLine.sales_invoice_id == invoice.id)
    )
    assert invoice_line is not None
    assert invoice_line.freight_amount == Decimal("20.0000")

    # An explicit zero waives it -- silence and zero are different answers.
    waived = DeliveryNoteService(session).create_note(
        DeliveryNoteCreate(
            sales_order_id=order.id,
            delivery_date=date(2026, 8, 6),
            freight_amount=Decimal("0"),
            lines=[
                DeliveryNoteLineWrite(
                    sales_order_line_id=order_line.id,
                    line_number=1,
                    current_delivery_quantity=Decimal("3"),
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=firm.id,
        actor_id=actor_id,
    )
    assert waived.freight_amount == Decimal("0.0000")
