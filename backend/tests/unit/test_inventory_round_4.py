"""Inventory round 4: the rules the owner agreed for the open batch rows.

D-STK-43: a batch number typed for a product that keeps no batches made a
batch. D-STK-48: a product that tracks expiry took a batch with no date.
D-STK-50: Add Serial numbered a unit without looking at the stock held.
"""

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.batch_serial.models.batch_serial import BatchRecord
from app.batch_serial.schemas.batch_serial import (
    BatchCreate,
    BatchUpdate,
    SerialCreate,
    SerialUpdate,
)
from app.batch_serial.services import BatchSerialService
from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.finance.models import AccountingPeriod
from app.finance.services.document_posting import (
    assert_stock_date_in_open_period,
)
from app.goods_receipt.models import GoodsReceiptLine
from app.goods_receipt.schemas import GoodsReceiptCreate
from app.goods_receipt.services import GoodsReceiptService
from app.inventory.models import InventoryRecord
from app.inventory.schemas.inventory import (
    PhysicalCountCreate,
    StockQuarantineCreate,
    StockTransferCreate,
    StockWriteOffCreate,
)
from app.inventory.services.inventory_service import InventoryService
from app.inventory.services.physical_count_service import PhysicalCountService
from app.inventory.services.repacking import RepackService, RepackWrite
from app.inventory.services.stock_transfers import (
    StockTransferService,
    StockTransferWrite,
)
from tests.unit import test_batch_serial_expiry as registers
from tests.unit.test_goods_receipt import _Fixture, _session_factory
from tests.unit.test_inventory_round_1_b import _Register
from tests.unit.test_purchase_chain_synthesis import _Firm
from tests.unit.test_sales_return_module import COST, _Dispatch, _stock_value
from tests.unit.test_sales_return_module import (
    _session_factory as _selling_sessions,
)

pytestmark = pytest.mark.typed_document_numbers


def _receive(fixture: _Fixture, **line: object) -> object:
    """Create a receipt of two of the order line with these line fields."""
    data = fixture.receipt_payload("2").model_dump()
    data["lines"][0].update(line)
    return GoodsReceiptService(fixture.session).create_receipt(
        GoodsReceiptCreate.model_validate(data),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )


def _complete(fixture: _Fixture, receipt: object) -> None:
    """Complete a receipt, which is what stocks it and makes its batch."""
    GoodsReceiptService(fixture.session).complete_receipt(
        receipt.id,  # type: ignore[attr-defined]
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
    )


def _batches(fixture: _Fixture) -> list[BatchRecord]:
    """Return every batch the firm has registered."""
    return list(
        fixture.session.scalars(
            select(BatchRecord).where(BatchRecord.firm_id == fixture.firm.id)
        )
    )


# ── D-STK-43: a batch typed for a product that keeps none ───────────────────


def test_a_batch_typed_for_an_untracked_product_is_ignored() -> None:
    """The receipt goes through, onto the product's own row, with no batch."""
    fixture = _Fixture(_session_factory()(), "R4UNT")
    receipt = _receive(fixture, batch_number="TYPED-1")

    _complete(fixture, receipt)

    assert _batches(fixture) == []
    line = fixture.session.scalar(
        select(GoodsReceiptLine).where(
            GoodsReceiptLine.goods_receipt_id == receipt.id  # type: ignore[attr-defined]
        )
    )
    assert line is not None
    assert (line.batch_number, line.batch_id) == ("TYPED-1", None)
    rows = list(
        fixture.session.scalars(
            select(InventoryRecord).where(
                InventoryRecord.product_id == fixture.product.id
            )
        )
    )
    assert [(row.batch_id, row.current_quantity) for row in rows] == [
        (None, Decimal("2"))
    ]


def test_a_batch_typed_for_a_tracked_product_is_still_registered() -> None:
    """The switch decides: the same line on a batch-tracked product."""
    fixture = _Fixture(_session_factory()(), "R4TRK")
    fixture.product.track_batch = True
    fixture.session.commit()

    _complete(fixture, _receive(fixture, batch_number="TYPED-2"))

    assert [row.batch_number for row in _batches(fixture)] == ["TYPED-2"]


# ── D-STK-48: an expiry date where the product tracks expiry ────────────────


def _dated_product(fixture: _Fixture) -> None:
    """Make the fixture's product one that tracks batch, expiry and make date."""
    for switch in ("track_batch", "track_expiry", "track_manufacturing_date"):
        setattr(fixture.product, switch, True)
    fixture.session.commit()


def test_a_receipt_refuses_a_batch_with_no_expiry_where_expiry_is_tracked() -> None:
    """Refused when it would be stocked, and nothing is stocked."""
    fixture = _Fixture(_session_factory()(), "R4EXP")
    _dated_product(fixture)
    receipt = _receive(fixture, batch_number="NO-DATE")

    with pytest.raises(ValidationError, match="batch NO-DATE needs an expiry date"):
        _complete(fixture, receipt)
    fixture.session.rollback()

    assert _batches(fixture) == []
    assert (
        fixture.session.scalar(
            select(InventoryRecord).where(
                InventoryRecord.product_id == fixture.product.id
            )
        )
        is None
    )


def test_a_receipt_with_a_shelf_life_needs_only_the_manufacturing_date() -> None:
    """The shelf life fills the expiry, so the batch is dated and taken."""
    fixture = _Fixture(_session_factory()(), "R4SHL")
    _dated_product(fixture)
    fixture.product.shelf_life_days = 30
    fixture.session.commit()

    _complete(
        fixture,
        _receive(fixture, batch_number="MADE", manufacturing_date=date(2026, 8, 1)),
    )

    assert [row.expiry_date for row in _batches(fixture)] == [date(2026, 8, 31)]


def test_a_later_delivery_dates_a_batch_registered_without_one() -> None:
    """An old undated batch takes the date typed, and is refused with none."""
    fixture = _Fixture(_session_factory()(), "R4OLD")
    _dated_product(fixture)
    old = BatchRecord(
        firm_id=fixture.firm.id,
        product_id=fixture.product.id,
        batch_number="OLD-1",
        status="AVAILABLE",
        created_by=fixture.actor_id,
        updated_by=fixture.actor_id,
    )
    fixture.session.add(old)
    fixture.session.commit()

    with pytest.raises(ValidationError, match="batch OLD-1 needs an expiry date"):
        _complete(fixture, _receive(fixture, batch_number="OLD-1"))
    fixture.session.rollback()

    _complete(
        fixture, _receive(fixture, batch_number="OLD-1", expiry_date=date(2027, 5, 1))
    )
    fixture.session.refresh(old)
    assert old.expiry_date == date(2027, 5, 1)


def test_the_batch_master_asks_for_the_expiry_of_a_dated_product() -> None:
    """On the way in, by shelf life where only the make date is typed, on edit."""
    books = _Register("R4BM")

    def create(number: str, **fields: object) -> BatchRecord:
        return books.service.create_batch(
            firm_scope=books.firm.id,
            actor_id=books.actor_id,
            data=BatchCreate.model_validate(
                {"product_id": books.product.id, "batch_number": number} | fields
            ),
        )

    with pytest.raises(ValidationError, match="batch BM-1 needs an expiry date"):
        create("BM-1")
    filled = create("BM-2", manufacturing_date="2026-08-01", shelf_life_days=10)
    assert filled.expiry_date == date(2026, 8, 11)

    with pytest.raises(ValidationError, match="batch BM-2 needs an expiry date"):
        books.service.update_batch(
            firm_scope=books.firm.id,
            actor_id=books.actor_id,
            batch_id=filled.id,
            data=BatchUpdate(expiry_date=None),
        )
    # A save that does not touch the date is not asked for it.
    filled.expiry_date = None
    books.session.commit()
    held = books.service.update_batch(
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
        batch_id=filled.id,
        data=BatchUpdate(remarks="held for a recall"),
    )
    assert held.remarks == "held for a recall"


def test_a_product_that_tracks_no_expiry_keeps_its_undated_batch() -> None:
    """The rule is the product's switch, not every batch's."""
    books = _Register("R4PNT")
    books.product.track_expiry = False
    books.session.commit()

    batch = books.service.create_batch(
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
        data=BatchCreate(product_id=books.product.id, batch_number="PAINT-1"),
    )

    assert batch.expiry_date is None


# ── D-STK-50: Add Serial stops at the stock held ────────────────────────────


def _two_on_the_shelf(code: str) -> _Register:
    """Build a register whose own warehouse holds two of the product."""
    books = _Register(code)
    registers._stock(books.session, books.warehouse, books.batch("SHELF"), "2")
    return books


def test_add_serial_is_refused_past_the_quantity_the_warehouse_holds() -> None:
    """Two held, two numbered, and the third is refused in words."""
    books = _two_on_the_shelf("R4SN")
    here = {"warehouse_id": books.warehouse.id}
    books.serial("U-1", **here)
    books.serial("U-2", **here)

    with pytest.raises(
        ValidationError, match="This warehouse holds 2 of .* and 2 are already"
    ):
        books.serial("U-3", **here)


def test_a_unit_that_has_left_is_not_counted_against_the_shelf() -> None:
    """A sold unit is a record of the past; it may not come back unseen."""
    books = _two_on_the_shelf("R4SO")
    here = {"warehouse_id": books.warehouse.id}
    books.serial("U-1", **here)
    gone = books.serial("U-OLD", status="SOLD", **here)
    books.serial("U-2", **here)

    with pytest.raises(ValidationError, match="another serial number cannot be added"):
        books.service.update_serial(
            firm_scope=books.firm.id,
            actor_id=books.actor_id,
            serial_id=gone.id,
            data=SerialUpdate.model_validate({"status": "AVAILABLE"}),
        )
    # An edit that leaves the unit where it stands is not judged.
    kept = books.service.update_serial(
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
        serial_id=gone.id,
        data=SerialUpdate(remarks="invoice 14"),
    )
    assert kept.remarks == "invoice 14"


def test_a_unit_naming_no_warehouse_is_judged_against_the_firm() -> None:
    """Everything the firm holds of the product, then refused."""
    session = registers._session_factory()()
    firm = registers._firm(session, "R4FW")
    product = registers._product(session, firm.id)
    registers._held(session, product, "1")
    service = BatchSerialService(session)

    def add(number: str) -> None:
        service.create_serial(
            firm_scope=firm.id,
            actor_id=uuid4(),
            data=SerialCreate(product_id=product.id, serial_number=number),
        )

    add("ONLY-1")
    with pytest.raises(ValidationError, match="The firm holds 1 of"):
        add("ONLY-2")


# ── D-STK-41: a movement that posts no journal still keeps to the periods ───


def _firm_with_books(code: str) -> _Firm:
    """Build a firm with open books holding ten of its product."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    built = _Firm(sessionmaker(bind=engine, expire_on_commit=False)(), code=code)
    built.stages(order=False, receipt=False)
    bills = built.bills()
    bill = bills.create_invoice(
        built.product_bill("10", "100"), firm_id=built.firm.id, actor_id=built.actor_id
    )
    bills.approve_invoice(bill.id, firm_scope=built.firm.id, actor_id=built.actor_id)
    assert built.session.scalar(
        select(AccountingPeriod.id).where(AccountingPeriod.firm_id == built.firm.id)
    )
    return built


def _stock_writes(firm: _Firm, on: date) -> dict[str, Callable[[], object]]:
    """Return each journal-less stock write, dated ``on``, ready to run."""
    session, firm_id, actor = firm.session, firm.firm.id, firm.actor_id
    place = {"branch_id": firm.branch.id, "product_id": firm.product.id}
    inventory = InventoryService(session)
    return {
        "transfer": lambda: inventory.transfer_stock(
            StockTransferCreate(
                **place,
                from_warehouse_id=firm.warehouse.id,
                to_warehouse_id=uuid4(),
                quantity=Decimal("1"),
                transaction_date=on,
            ),
            firm_scope=firm_id,
            actor_id=actor,
        ),
        "quarantine": lambda: inventory.quarantine_stock(
            StockQuarantineCreate(
                **place,
                warehouse_id=firm.warehouse.id,
                action="HOLD",
                quantity=Decimal("1"),
                transaction_date=on,
            ),
            firm_scope=firm_id,
            actor_id=actor,
        ),
        "transfer document": lambda: StockTransferService(session).create(
            StockTransferWrite(
                transfer_date=on,
                from_warehouse_id=firm.warehouse.id,
                to_warehouse_id=uuid4(),
                lines=[{"product_id": firm.product.id, "quantity": "1"}],
            ),
            firm_id=firm_id,
            actor_id=actor,
        ),
        "count": lambda: PhysicalCountService(session).create(
            PhysicalCountCreate(
                branch_id=firm.branch.id, warehouse_id=firm.warehouse.id, count_date=on
            ),
            firm_id=firm_id,
            actor_id=actor,
        ),
        "repack": lambda: RepackService(session).post(
            RepackWrite(
                repack_date=on,
                branch_id=firm.branch.id,
                warehouse_id=firm.warehouse.id,
                lines=[
                    {"kind": "CONSUME", "product_id": firm.product.id, "quantity": "1"},
                    {"kind": "PRODUCE", "product_id": uuid4(), "quantity": "1"},
                ],
            ),
            firm_id=firm_id,
            actor_id=actor,
        ),
    }


@pytest.mark.parametrize(
    ("on", "says"),
    [
        # Ahead of today is refused as that, before any period is asked
        # about (D-STK-66); behind the books, as outside an open period.
        (date(2030, 1, 1), "after today"),
        (date(1999, 1, 1), "No open accounting period"),
    ],
)
def test_a_stock_move_outside_an_open_period_is_refused(on: date, says: str) -> None:
    """Every write that posts no journal is refused, and nothing moves."""
    firm = _firm_with_books("R4DAT")

    for name, write in _stock_writes(firm, on).items():
        with pytest.raises(ValidationError, match=says):
            write()
        firm.session.rollback()
        assert name

    row = firm.session.scalar(
        select(InventoryRecord).where(InventoryRecord.product_id == firm.product.id)
    )
    assert row is not None
    assert (row.current_quantity, row.quarantine_quantity) == (Decimal("10"), 0)


def test_a_stock_move_inside_an_open_period_goes_through() -> None:
    """The rule reads the date and nothing else: a hold dated in the year."""
    firm = _firm_with_books("R4DIN")

    _stock_writes(firm, date(2026, 8, 12))["quarantine"]()

    row = firm.session.scalar(
        select(InventoryRecord).where(InventoryRecord.product_id == firm.product.id)
    )
    assert row is not None
    assert (row.current_quantity, row.quarantine_quantity) == (Decimal("9"), 1)


def test_a_firm_with_no_books_keeps_any_date() -> None:
    """A firm with stock and no accounts has no period to be inside.

    Any date up to today, that is: one ahead of it is refused with or
    without books (D-STK-66).
    """
    firm = _firm_with_books("R4NOB")

    assert_stock_date_in_open_period(
        firm.session, uuid4(), date(1999, 1, 1), what="A transfer"
    )
    with pytest.raises(ValidationError, match="after today"):
        assert_stock_date_in_open_period(
            firm.session, uuid4(), date(2030, 1, 1), what="A transfer"
        )
    for period in firm.session.scalars(
        select(AccountingPeriod).where(AccountingPeriod.firm_id == firm.firm.id)
    ):
        period.is_deleted = True
    firm.session.commit()

    _stock_writes(firm, date(1999, 1, 1))["quarantine"]()

    held = firm.session.scalar(
        select(InventoryRecord.quarantine_quantity).where(
            InventoryRecord.product_id == firm.product.id
        )
    )
    assert held == 1


# --- D-STK-46: what came back as scrap can be written off -------------------


def _row(setup: _Dispatch) -> InventoryRecord:
    """Read the one stock row the dispatch fixture trades on."""
    row = setup.session.scalar(
        select(InventoryRecord).where(
            InventoryRecord.firm_id == setup.firm.id,
            InventoryRecord.product_id == setup.product.id,
        )
    )
    assert row is not None
    return row


def _write_off(setup: _Dispatch, quantity: str, reason: str = "DAMAGE") -> object:
    """Write ``quantity`` of the fixture's product off."""
    return InventoryService(setup.session).write_off_stock(
        StockWriteOffCreate(
            branch_id=setup.branch.id,
            warehouse_id=setup.warehouse.id,
            product_id=setup.product.id,
            reason=reason,
            customer_id=(setup.customer.id if reason == "FREE_TO_CUSTOMER" else None),
            quantity=Decimal(quantity),
            transaction_date=date(2026, 8, 6),
        ),
        firm_scope=setup.firm.id,
        actor_id=setup.actor_id,
    )


def test_units_returned_as_scrap_land_in_the_damaged_bucket() -> None:
    """They were valued and stood in no bucket, so nothing could reach them."""
    setup = _Dispatch(_selling_sessions()())
    shelf = _row(setup).current_quantity

    setup.completed(quantity=Decimal("2"), scrap=Decimal("2"))

    row = _row(setup)
    assert (row.current_quantity, row.damaged_quantity) == (shelf, 2)


def test_scrap_and_damage_share_the_bucket_and_cancel_out_of_it() -> None:
    """A cancelled return takes back exactly what it put there."""
    setup = _Dispatch(_selling_sessions()())
    value = _stock_value(
        setup.session, firm_id=setup.firm.id, product_id=setup.product.id
    )

    service, row = setup.completed(
        quantity=Decimal("3"), damaged=Decimal("1"), scrap=Decimal("1")
    )
    assert _row(setup).damaged_quantity == 2
    service.cancel_return(
        row.id, firm_scope=setup.firm.id, actor_id=setup.actor_id, reason="error"
    )

    assert _row(setup).damaged_quantity == 0
    assert (
        _stock_value(setup.session, firm_id=setup.firm.id, product_id=setup.product.id)
        == value
    )


def test_a_write_off_takes_returned_scrap_before_the_shelf() -> None:
    """The condemned units go first, and their value leaves with them."""
    setup = _Dispatch(_selling_sessions()())
    setup.completed(quantity=Decimal("2"), scrap=Decimal("2"))
    shelf = _row(setup).current_quantity
    value = _stock_value(
        setup.session, firm_id=setup.firm.id, product_id=setup.product.id
    )

    movement = _write_off(setup, "2")

    row = _row(setup)
    assert (row.current_quantity, row.damaged_quantity) == (shelf, 0)
    assert movement.damaged_quantity_delta == -2  # type: ignore[attr-defined]
    assert (
        _stock_value(setup.session, firm_id=setup.firm.id, product_id=setup.product.id)
        == value - COST * 2
    )


def test_a_write_off_past_the_scrap_goes_on_into_the_shelf() -> None:
    """Three written off against two condemned takes the third from stock."""
    setup = _Dispatch(_selling_sessions()())
    setup.completed(quantity=Decimal("2"), scrap=Decimal("2"))
    shelf = _row(setup).current_quantity

    _write_off(setup, "3")

    row = _row(setup)
    assert (row.current_quantity, row.damaged_quantity) == (shelf - 1, 0)


def test_a_write_off_is_refused_past_shelf_and_scrap_together() -> None:
    """The figure it names counts the condemned units too."""
    setup = _Dispatch(_selling_sessions()())
    setup.completed(quantity=Decimal("2"), scrap=Decimal("2"))
    held = _row(setup).current_quantity + 2

    with pytest.raises(ValidationError) as refusal:
        _write_off(setup, str(held + 1))

    assert f"holds {held}" in refusal.value.message


def test_goods_given_to_a_customer_never_come_out_of_the_scrap() -> None:
    """Free goods are good goods: they leave the shelf, not the damaged pile."""
    setup = _Dispatch(_selling_sessions()())
    setup.completed(quantity=Decimal("2"), scrap=Decimal("2"))
    shelf = _row(setup).current_quantity

    _write_off(setup, "1", reason="FREE_TO_CUSTOMER")

    row = _row(setup)
    assert (row.current_quantity, row.damaged_quantity) == (shelf - 1, 2)


def test_damage_that_arrived_blocked_on_the_shelf_is_not_counted_twice() -> None:
    """A receipt's damaged units are in current stock already."""
    setup = _Dispatch(_selling_sessions()())
    row = _row(setup)
    row.current_quantity += 2
    row.blocked_quantity += 2
    row.damaged_quantity += 2
    setup.session.commit()

    assert InventoryService._damaged_off_the_shelf(row) == 0
