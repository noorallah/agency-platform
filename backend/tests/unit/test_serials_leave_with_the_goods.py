"""A serialised unit's status moves with the stock it is part of (D-STK-4).

Nothing outside ``app/batch_serial`` read or wrote ``serial_numbers``, so a
mixer grinder that left on a delivery note kept its serial ``AVAILABLE`` for
ever. The owner decided on 2026-09-18 that the storekeeper picks the units:
the note line names them, dispatch refuses until there is one per unit
leaving, and each becomes ``SOLD``; a sales return names the units coming back
and completing it makes them ``AVAILABLE`` again.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.batch_serial.models import BatchRecord, DocumentLineSerial, SerialNumber
from app.branches.models import Branch, Warehouse
from app.common.audit.models import AuditLog
from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.customers.models import Customer
from app.delivery_note.models import DeliveryNote, DeliveryNoteLine
from app.delivery_note.schemas import (
    DeliveryNoteCreate,
    DeliveryNoteLineWrite,
    DeliveryNoteStatus,
)
from app.delivery_note.services import DeliveryNoteService
from app.finance.services.opening_setup import seed_finance_setup
from app.firms.models import Firm
from app.inventory.models import InventoryTransaction
from app.inventory.schemas import InventoryAdjustmentCreate
from app.inventory.services import InventoryService
from app.products.models import Product
from app.sales_invoice.schemas import (
    SalesInvoiceCreate,
    SalesInvoiceLineWrite,
    SalesInvoiceSourceType,
)
from app.sales_invoice.services import SalesInvoiceService
from app.sales_order.models import SalesOrderLine
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services import SalesOrderService
from app.sales_return.models import SalesReturn
from app.sales_return.schemas import (
    SalesReturnCreate,
    SalesReturnLineWrite,
    SalesReturnSourceType,
)
from app.sales_return.services import SalesReturnService

ON = date(2026, 8, 4)


def _session() -> Session:
    """Build an in-memory store holding every table."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


class _Shop:
    """A firm with a serialised product on the shelf and an order to ship."""

    def __init__(self, session: Session, *, serialised: bool = True) -> None:
        """Stock five units, number them, and approve an order for two."""
        self.session = session
        self.actor = uuid4()
        self.firm = Firm(
            name="Serial Firm",
            code="SER-FIRM",
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
        )
        session.add(self.firm)
        session.commit()
        seed_finance_setup(
            session,
            firm_id=self.firm.id,
            year_starts_on=date(2026, 4, 1),
            actor_id=self.actor,
        )
        self.branch = Branch(
            firm_id=self.firm.id,
            code="HO",
            name="Head Office",
            display_name="Head Office",
            currency_code="INR",
            working_hours={"start": "09:00", "end": "18:00"},
            status="ACTIVE",
        )
        session.add(self.branch)
        session.commit()
        self.warehouse = self._warehouse("MAIN")
        self.customer = Customer(
            firm_id=self.firm.id,
            code="CUS-1",
            customer_type="RETAIL",
            name="Anand Electricals",
            display_name="Anand Electricals",
            currency_code="INR",
            status="ACTIVE",
            credit_limit=Decimal("500000"),
            opening_balance=Decimal("0"),
        )
        self.product = self._product("MIX", serialised=serialised)
        session.add(self.customer)
        session.commit()
        self._stock(self.product, self.warehouse, Decimal("5"))
        self.serials = [
            self.serial(f"MIX-{n:04d}", self.product, self.warehouse)
            for n in range(1, 6)
        ]
        self.order_line = self.order(self.product, Decimal("2"))

    def _warehouse(self, code: str) -> Warehouse:
        """Add a warehouse to the head office."""
        row = Warehouse(
            firm_id=self.firm.id,
            branch_id=self.branch.id,
            code=code,
            name=code,
            display_name=code,
            status="ACTIVE",
        )
        self.session.add(row)
        self.session.commit()
        return row

    def _product(self, code: str, *, serialised: bool) -> Product:
        """Add a product, tracked by serial or not."""
        row = Product(
            firm_id=self.firm.id,
            code=code,
            name=f"Product {code}",
            product_type="STOCK_ITEM",
            status="ACTIVE",
            track_serial=serialised,
        )
        self.session.add(row)
        self.session.commit()
        return row

    def _stock(self, product: Product, warehouse: Warehouse, quantity: Decimal) -> None:
        """Put stock on a shelf at a cost, so the journals have a value."""
        inventory = InventoryService(self.session)
        valuation = inventory.valuation_for(
            firm_scope=self.firm.id, product_id=product.id
        )
        valuation.average_cost = Decimal("2000")
        self.session.commit()
        inventory.create_adjustment(
            InventoryAdjustmentCreate(
                branch_id=self.branch.id,
                warehouse_id=warehouse.id,
                product_id=product.id,
                quantity=quantity,
                reference_number=f"ADJ-{product.code}-{uuid4().hex[:8]}",
                reference_type="ADJUSTMENT",
                transaction_date=date(2026, 8, 3),
            ),
            firm_scope=self.firm.id,
            actor_id=self.actor,
        )

    def serial(
        self,
        number: str,
        product: Product,
        warehouse: Warehouse,
        *,
        status: str = "AVAILABLE",
    ) -> SerialNumber:
        """Give one unit on a shelf its serial number."""
        row = SerialNumber(
            firm_id=self.firm.id,
            product_id=product.id,
            warehouse_id=warehouse.id,
            branch_id=self.branch.id,
            serial_number=number,
            status=status,
        )
        self.session.add(row)
        self.session.commit()
        return row

    def order(self, product: Product, quantity: Decimal) -> SalesOrderLine:
        """Raise and approve an order, returning its only line."""
        orders = SalesOrderService(self.session)
        order = orders.create_order(
            SalesOrderCreate(
                customer_id=self.customer.id,
                branch_id=self.branch.id,
                warehouse_id=self.warehouse.id,
                order_date=date(2026, 8, 3),
                lines=[
                    SalesOrderLineWrite(
                        line_number=1,
                        product_id=product.id,
                        quantity=quantity,
                        unit_price=Decimal("3000"),
                    )
                ],
            ),
            firm_id=self.firm.id,
            actor_id=self.actor,
        )
        orders.approve_order(order.id, firm_scope=self.firm.id, actor_id=self.actor)
        line = self.session.scalar(
            select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order.id)
        )
        assert line is not None
        return line

    def note(
        self,
        serial_ids: list[UUID] | None,
        *,
        order_line: SalesOrderLine | None = None,
        quantity: Decimal = Decimal("2"),
    ) -> DeliveryNote:
        """Raise and approve a note shipping the order line."""
        line = order_line or self.order_line
        service = DeliveryNoteService(self.session)
        note = service.create_note(
            DeliveryNoteCreate(
                sales_order_id=line.sales_order_id,
                delivery_date=ON,
                lines=[
                    DeliveryNoteLineWrite(
                        sales_order_line_id=line.id,
                        line_number=1,
                        current_delivery_quantity=quantity,
                        unit_price=Decimal("3000"),
                        serial_ids=serial_ids,
                    )
                ],
            ),
            firm_id=self.firm.id,
            actor_id=self.actor,
        )
        return service.approve_note(
            note.id, firm_scope=self.firm.id, actor_id=self.actor
        )

    def dispatch(self, note: DeliveryNote) -> DeliveryNote:
        """Dispatch a note, as the Dispatch button does."""
        return DeliveryNoteService(self.session).dispatch_note(
            note.id, firm_scope=self.firm.id, actor_id=self.actor
        )

    def note_line(self, note: DeliveryNote) -> DeliveryNoteLine:
        """Return a note's only line."""
        line = self.session.scalar(
            select(DeliveryNoteLine).where(DeliveryNoteLine.delivery_note_id == note.id)
        )
        assert line is not None
        return line

    def status(self, serial: SerialNumber) -> str:
        """Read a unit's status as the store holds it."""
        self.session.refresh(serial)
        return serial.status

    def dispatch_movements(self) -> list[InventoryTransaction]:
        """Every DISPATCH movement the store holds."""
        return list(
            self.session.scalars(
                select(InventoryTransaction).where(
                    InventoryTransaction.transaction_type == "DISPATCH"
                )
            ).all()
        )

    def return_of(
        self,
        note: DeliveryNote,
        serial_ids: list[UUID] | None,
        *,
        quantity: Decimal = Decimal("1"),
    ) -> SalesReturn:
        """Raise and approve a return of part of a dispatched note."""
        service = SalesReturnService(self.session)
        row = service.create_return(
            SalesReturnCreate(
                warehouse_id=self.warehouse.id,
                return_date=date(2026, 8, 5),
                lines=[
                    SalesReturnLineWrite(
                        source_document_type=SalesReturnSourceType.DELIVERY_NOTE,
                        source_document_id=note.id,
                        source_document_line_id=self.note_line(note).id,
                        line_number=1,
                        current_return_quantity=quantity,
                        unit_price=Decimal("3000"),
                        serial_ids=serial_ids,
                    )
                ],
            ),
            firm_id=self.firm.id,
            actor_id=self.actor,
        )
        return service.approve_return(
            row.id, firm_scope=self.firm.id, actor_id=self.actor
        )

    def complete(self, row: SalesReturn) -> SalesReturn:
        """Complete a return, which is when the goods come back."""
        return SalesReturnService(self.session).complete_return(
            row.id, firm_scope=self.firm.id, actor_id=self.actor
        )

    def ids(self, *indexes: int) -> list[UUID]:
        """Return the ids of the numbered units at these positions."""
        return [self.serials[index].id for index in indexes]


# ---- dispatch ------------------------------------------------------------


def test_dispatch_marks_the_picked_units_sold() -> None:
    """The defect itself: two units leave, and exactly those two read SOLD."""
    shop = _Shop(_session())
    note = shop.dispatch(shop.note(shop.ids(0, 2)))

    assert note.status == DeliveryNoteStatus.DISPATCHED.value
    assert [shop.status(serial) for serial in shop.serials] == [
        "SOLD",
        "AVAILABLE",
        "SOLD",
        "AVAILABLE",
        "AVAILABLE",
    ]
    assert shop.serials[0].current_owner == "Anand Electricals"
    # Each unit names the movement that carried it, and says when it moved.
    (movement,) = shop.dispatch_movements()
    picks = shop.session.scalars(select(DocumentLineSerial)).all()
    assert {pick.inventory_transaction_id for pick in picks} == {movement.id}
    assert all(pick.moved_at is not None for pick in picks)
    # A movement of two units cannot name one serial.
    assert movement.serial_id is None
    sold = shop.session.scalars(
        select(AuditLog).where(AuditLog.action == "serial_number.sold")
    ).all()
    assert {row.entity_id for row in sold} == set(shop.ids(0, 2))


def test_the_note_shows_which_units_went() -> None:
    """The read model lists the units, so the screen can say what left."""
    shop = _Shop(_session())
    note = shop.dispatch(shop.note(shop.ids(1, 3)))

    response = DeliveryNoteService(shop.session).note_response(note)
    (line,) = response.lines
    assert [unit.serial_number for unit in line.serials] == ["MIX-0002", "MIX-0004"]
    assert {unit.status for unit in line.serials} == {"SOLD"}


def test_a_single_unit_movement_names_its_serial() -> None:
    """Where a movement carried one unit, the ledger row names it too."""
    shop = _Shop(_session())
    shop.dispatch(shop.note(shop.ids(4), quantity=Decimal("1")))

    (movement,) = shop.dispatch_movements()
    assert movement.serial_id == shop.serials[4].id


def test_dispatch_is_refused_until_every_unit_is_picked() -> None:
    """One serial for two units: refused by line, with the shortfall named."""
    shop = _Shop(_session())
    note = shop.note(shop.ids(0))

    with pytest.raises(ValidationError, match=r"Line 1 \(MIX\).*pick 1 more"):
        shop.dispatch(note)

    shop.session.rollback()
    shop.session.refresh(note)
    assert note.status == DeliveryNoteStatus.APPROVED.value
    assert shop.dispatch_movements() == []
    assert shop.status(shop.serials[0]) == "AVAILABLE"


def test_dispatch_is_refused_with_no_units_picked() -> None:
    """A note saved without picks -- an older client -- cannot ship either."""
    shop = _Shop(_session())
    note = shop.note(None)

    with pytest.raises(ValidationError, match="0 serial numbers are picked"):
        shop.dispatch(note)


def test_dispatch_is_refused_with_too_many_units_picked() -> None:
    """Three serials for two units would mark a unit sold that never left."""
    shop = _Shop(_session())
    note = shop.note(shop.ids(0, 1, 2))

    with pytest.raises(ValidationError, match="remove 1"):
        shop.dispatch(note)


def test_a_unit_picked_twice_is_refused() -> None:
    """The same serial twice would count one unit as two."""
    shop = _Shop(_session())

    with pytest.raises(ValidationError, match="picked twice"):
        shop.note(shop.ids(0, 0))


def test_a_unit_of_another_product_is_refused() -> None:
    """A serial belongs to one product; it cannot stand in for another."""
    shop = _Shop(_session())
    other = shop._product("TV", serialised=True)
    stranger = shop.serial("TV-0001", other, shop.warehouse)

    with pytest.raises(ValidationError, match="belongs to another product"):
        shop.note([shop.serials[0].id, stranger.id])


def test_a_unit_in_another_warehouse_is_refused() -> None:
    """The unit has to be on the shelf the line ships from."""
    shop = _Shop(_session())
    elsewhere = shop._warehouse("SECOND")
    away = shop.serial("MIX-0099", shop.product, elsewhere)

    with pytest.raises(ValidationError, match="not in the warehouse"):
        shop.note([shop.serials[0].id, away.id])


def test_a_unit_already_sold_is_refused() -> None:
    """A SOLD unit is with a customer; it cannot leave a second time."""
    shop = _Shop(_session())
    gone = shop.serial("MIX-0100", shop.product, shop.warehouse, status="SOLD")

    with pytest.raises(ValidationError, match="is SOLD, not AVAILABLE"):
        shop.note([shop.serials[0].id, gone.id])


def test_two_notes_cannot_both_ship_one_unit() -> None:
    """Both drafts may name it; only the first to ship may take it."""
    shop = _Shop(_session())
    # Enough on the shelf that stock is not what refuses the second note.
    shop._stock(shop.product, shop.warehouse, Decimal("10"))
    second_line = shop.order(shop.product, Decimal("2"))
    first = shop.note(shop.ids(0, 1))
    second = shop.note(shop.ids(1, 2), order_line=second_line)
    shop.dispatch(first)

    with pytest.raises(ValidationError, match="MIX-0002 is SOLD"):
        shop.dispatch(second)


def test_a_product_nobody_serialises_is_unaffected() -> None:
    """No picks, no refusal, and no serial ever moves."""
    shop = _Shop(_session(), serialised=False)
    note = shop.dispatch(shop.note(None))

    assert note.status == DeliveryNoteStatus.DISPATCHED.value
    assert {shop.status(serial) for serial in shop.serials} == {"AVAILABLE"}
    assert shop.session.scalars(select(DocumentLineSerial)).all() == []


def test_a_product_nobody_serialises_takes_no_serials() -> None:
    """Naming a unit on such a line is a mistake, not a preference."""
    shop = _Shop(_session(), serialised=False)

    with pytest.raises(ValidationError, match="not serial-tracked"):
        shop.note(shop.ids(0, 1))


# ---- returns -------------------------------------------------------------


def test_a_completed_return_puts_the_units_back_on_the_shelf() -> None:
    """The unit that came back reads AVAILABLE again; the other stays SOLD."""
    shop = _Shop(_session())
    note = shop.dispatch(shop.note(shop.ids(0, 1)))
    shop.complete(shop.return_of(note, shop.ids(1)))

    assert shop.status(shop.serials[0]) == "SOLD"
    assert shop.status(shop.serials[1]) == "AVAILABLE"
    assert shop.serials[1].current_owner is None
    assert shop.serials[1].warehouse_id == shop.warehouse.id
    returned = shop.session.scalar(
        select(InventoryTransaction).where(
            InventoryTransaction.transaction_type == "SALES_RETURN"
        )
    )
    assert returned is not None
    assert returned.serial_id == shop.serials[1].id


def test_the_return_picker_offers_what_went_out_on_that_line() -> None:
    """Only units dispatched on the source line and still out are offered."""
    shop = _Shop(_session())
    note = shop.dispatch(shop.note(shop.ids(0, 1)))

    offered = SalesReturnService(shop.session).returnable_serials(
        firm_scope=shop.firm.id,
        source_document_type="DELIVERY_NOTE",
        source_document_line_id=shop.note_line(note).id,
    )
    assert offered.serial_tracked
    assert [unit.serial_number for unit in offered.serials] == [
        "MIX-0001",
        "MIX-0002",
    ]


def test_a_return_cannot_name_a_unit_that_never_left() -> None:
    """A unit still on the shelf is not the customer's to send back."""
    shop = _Shop(_session())
    note = shop.dispatch(shop.note(shop.ids(0, 1)))

    with pytest.raises(ValidationError, match="MIX-0005 is AVAILABLE, not SOLD"):
        shop.return_of(note, shop.ids(4))


def test_completing_a_return_needs_one_unit_per_unit_returned() -> None:
    """Two units back and one serial named is refused at completion."""
    shop = _Shop(_session())
    note = shop.dispatch(shop.note(shop.ids(0, 1)))
    row = shop.return_of(note, shop.ids(0), quantity=Decimal("2"))

    with pytest.raises(ValidationError, match=r"brings back 2 .*pick 1 more"):
        shop.complete(row)


def test_cancelling_a_completed_return_sends_the_units_back_out() -> None:
    """The stock leaves the shelf again, so its units are SOLD again."""
    shop = _Shop(_session())
    note = shop.dispatch(shop.note(shop.ids(0, 1)))
    row = shop.complete(shop.return_of(note, shop.ids(1)))
    assert shop.status(shop.serials[1]) == "AVAILABLE"

    SalesReturnService(shop.session).cancel_return(
        row.id, firm_scope=shop.firm.id, actor_id=shop.actor, reason="Keyed twice"
    )

    assert shop.status(shop.serials[1]) == "SOLD"
    assert shop.serials[1].current_owner == "Anand Electricals"


def test_a_return_cannot_be_cancelled_once_its_unit_is_sold_again() -> None:
    """The stock could leave, but the unit it names is someone else's now."""
    shop = _Shop(_session())
    note = shop.dispatch(shop.note(shop.ids(0, 1)))
    row = shop.complete(shop.return_of(note, shop.ids(1)))
    again = shop.order(shop.product, Decimal("1"))
    shop.dispatch(shop.note(shop.ids(1), order_line=again, quantity=Decimal("1")))

    with pytest.raises(ValidationError, match="can no longer be cancelled"):
        SalesReturnService(shop.session).cancel_return(
            row.id, firm_scope=shop.firm.id, actor_id=shop.actor
        )


def test_editing_a_draft_return_keeps_its_units_unless_told_otherwise() -> None:
    """Absent means leave alone; an empty list clears.

    A return's lines are re-inserted on every save, so the units they named
    are carried across by line number rather than lost with the old ids.
    """
    shop = _Shop(_session())
    note = shop.dispatch(shop.note(shop.ids(0, 1)))
    service = SalesReturnService(shop.session)

    def _payload(serial_ids: list[UUID] | None) -> SalesReturnCreate:
        """Return one unit of the note's line, naming these units."""
        return SalesReturnCreate(
            warehouse_id=shop.warehouse.id,
            return_date=date(2026, 8, 5),
            lines=[
                SalesReturnLineWrite(
                    source_document_type=SalesReturnSourceType.DELIVERY_NOTE,
                    source_document_id=note.id,
                    source_document_line_id=shop.note_line(note).id,
                    line_number=1,
                    current_return_quantity=Decimal("1"),
                    serial_ids=serial_ids,
                )
            ],
        )

    row = service.create_return(
        _payload(shop.ids(0)), firm_id=shop.firm.id, actor_id=shop.actor
    )

    def _edit(serial_ids: list[UUID] | None) -> list[str]:
        """Save the draft again and read back the units it names."""
        service.update_return(
            row.id, _payload(serial_ids), firm_scope=shop.firm.id, actor_id=shop.actor
        )
        (line,) = service.return_response(row).lines
        return [unit.serial_number for unit in line.serials]

    assert _edit(None) == ["MIX-0001"]
    assert _edit([]) == []


def test_a_bill_of_a_dispatched_note_names_no_serials() -> None:
    """The units were picked on the note; a bill cannot re-pick them."""
    shop = _Shop(_session())
    note = shop.dispatch(shop.note(shop.ids(0, 1)))

    with pytest.raises(ValidationError, match="picked on the delivery note"):
        SalesInvoiceService(shop.session).create_invoice(
            SalesInvoiceCreate(
                invoice_date=ON,
                lines=[
                    SalesInvoiceLineWrite(
                        source_document_type=SalesInvoiceSourceType.DELIVERY_NOTE,
                        source_document_id=note.id,
                        source_document_line_id=shop.note_line(note).id,
                        line_number=1,
                        current_invoice_quantity=Decimal("2"),
                        serial_ids=shop.ids(2, 3),
                    )
                ],
            ),
            firm_id=shop.firm.id,
            actor_id=shop.actor,
        )


def _batched_tv(shop: _Shop) -> tuple[Product, dict[str, SerialNumber]]:
    """Stock a batch- and serial-tracked product in three batches.

    One unit each: an expired batch, one expiring soon and one late, so the
    allocator left alone would pick the early one.
    """
    tv = shop._product("TV", serialised=True)
    tv.track_batch = True
    shop.session.commit()
    units: dict[str, SerialNumber] = {}
    for number, expiry in (
        ("OLD", date(2026, 7, 1)),
        ("EARLY", date(2027, 1, 31)),
        ("LATE", date(2027, 12, 31)),
    ):
        batch = BatchRecord(
            firm_id=shop.firm.id,
            product_id=tv.id,
            batch_number=number,
            expiry_date=expiry,
            status="AVAILABLE",
        )
        shop.session.add(batch)
        shop.session.flush()
        InventoryService(shop.session).record_goods_receipt(
            firm_scope=shop.firm.id,
            actor_id=shop.actor,
            branch_id=shop.branch.id,
            warehouse_id=shop.warehouse.id,
            storage_node_id=None,
            product_id=tv.id,
            reference_number=f"GRN-{number}",
            transaction_date=date(2026, 6, 1),
            total_quantity=Decimal("1"),
            unit_cost=Decimal("0"),
            batch_id=batch.id,
        )
        unit = shop.serial(f"TV-{number}", tv, shop.warehouse)
        unit.batch_id = batch.id
        units[number] = unit
    shop.session.commit()
    return tv, units


def test_a_unit_leaves_from_its_own_batch() -> None:
    """The unit named decides the batch, not the earliest expiry.

    The allocator would draw the EARLY batch; the storekeeper handed over the
    unit from LATE, so LATE is what the movement and the ledger must say.
    """
    shop = _Shop(_session())
    tv, units = _batched_tv(shop)
    line = shop.order(tv, Decimal("1"))
    shop.dispatch(shop.note([units["LATE"].id], order_line=line, quantity=Decimal("1")))

    movement = shop.session.scalar(
        select(InventoryTransaction).where(
            InventoryTransaction.transaction_type == "DISPATCH",
            InventoryTransaction.product_id == tv.id,
        )
    )
    assert movement is not None
    assert movement.batch_id == units["LATE"].batch_id
    assert movement.serial_id == units["LATE"].id
    assert shop.status(units["LATE"]) == "SOLD"
    assert shop.status(units["EARLY"]) == "AVAILABLE"


def test_a_unit_in_an_expired_batch_is_refused_by_name() -> None:
    """Expired stock does not ship, whichever way it was chosen."""
    shop = _Shop(_session())
    tv, units = _batched_tv(shop)
    line = shop.order(tv, Decimal("1"))
    note = shop.note([units["OLD"].id], order_line=line, quantity=Decimal("1"))

    with pytest.raises(ValidationError, match="TV-OLD is in batch OLD, which expired"):
        shop.dispatch(note)
