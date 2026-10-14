"""Stock arriving in lots (L2 step 3).

`docs/design/LOT_COST_DESIGN.md`, section 3.3. Every batch is given our own
running reference, whatever the firm's costing method. A firm costing by lot
takes each stocked receipt line, and each opening stock line, into a lot of
its own; a firm on Average joins a batch by its number exactly as before.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.batch_serial.models import BatchRecord
from app.branches.models import Warehouse
from app.core.exceptions import ValidationError
from app.goods_receipt.models import GoodsReceipt, GoodsReceiptLine
from app.goods_receipt.services import GoodsReceiptService
from app.inventory.models import (
    BatchValuation,
    InventoryRecord,
    OpeningStockBatch,
    ProductValuation,
    StockLotSettings,
)
from app.inventory.schemas import OpeningStockBatchCreate
from app.inventory.services import InventoryService
from app.inventory.services.inventory_service import COSTING_BY_LOT
from app.inventory.services.lots import FIRM_BY_LOT, costs_by_lot
from app.inventory.services.opening_stock_import import template_csv
from app.products.models import Product
from tests.unit.test_goods_receipt import _Fixture, _session_factory
from tests.unit.test_opening_stock_import_file import (
    _ON,
    _csv,
    _factory,
    _firm,
    _run,
)

# The receipt fixture types its order number; see conftest (D-CFG-2).
pytestmark = pytest.mark.typed_document_numbers


def _by_lot(session: Session, firm_id: UUID) -> None:
    """Put the firm on costing by lot, as the switch-over will."""
    session.add(StockLotSettings(firm_id=firm_id, costing_method=FIRM_BY_LOT))
    session.commit()


def _shop(code: str, *, by_lot: bool, track_batch: bool = True) -> _Fixture:
    """Open a firm with an approved order for ten of one product at 100.00."""
    fixture = _Fixture(_session_factory()(), code)
    fixture.product.track_batch = track_batch
    fixture.session.commit()
    if by_lot:
        _by_lot(fixture.session, fixture.firm.id)
    return fixture


def _receive(fixture: _Fixture, quantity: str, **line: object) -> GoodsReceipt:
    """Create and complete one receipt of the order's line."""
    payload = fixture.receipt_payload(quantity)
    values = payload.model_dump()
    values["lines"][0].update(line)
    service = GoodsReceiptService(fixture.session)
    receipt = service.create_receipt(
        type(payload).model_validate(values),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    service.complete_receipt(
        receipt.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )
    fixture.session.expire_all()
    return receipt


def _batches(session: Session, *, deleted: bool = False) -> list[BatchRecord]:
    """Return the batches in the order they were made."""
    statement = select(BatchRecord).order_by(BatchRecord.lot_reference)
    if not deleted:
        statement = statement.where(BatchRecord.is_deleted.is_(False))
    return list(session.scalars(statement).all())


def _worth(session: Session, lot: BatchRecord) -> tuple[Decimal, Decimal]:
    """Return what a lot holds and what that is worth."""
    row = session.scalars(
        select(BatchValuation).where(BatchValuation.batch_id == lot.id)
    ).one()
    return Decimal(row.quantity_on_hand), Decimal(row.total_value)


def test_a_firm_with_no_setting_costs_on_average() -> None:
    """No row means Average, which is every firm until it switches."""
    fixture = _shop("LOT0", by_lot=False)

    assert costs_by_lot(fixture.session, fixture.firm.id) is False
    _by_lot(fixture.session, fixture.firm.id)
    assert costs_by_lot(fixture.session, fixture.firm.id) is True


def test_a_firm_on_average_still_joins_the_batch_by_its_number() -> None:
    """Two deliveries of one printed batch are one batch, now with a reference."""
    fixture = _shop("LOT1", by_lot=False)

    _receive(fixture, "4", batch_number="BN-1")
    _receive(fixture, "3", batch_number="BN-1")

    (batch,) = _batches(fixture.session)
    assert batch.per_purchase_line is False
    assert batch.has_printed_batch is True
    assert batch.source_document_type is None
    assert batch.lot_reference.startswith("LOT")
    assert fixture.session.scalars(select(BatchValuation)).all() == []
    item = fixture.session.scalars(select(ProductValuation)).one()
    assert item.costing_method != COSTING_BY_LOT
    assert Decimal(item.quantity_on_hand) == Decimal("7")


def test_every_receipt_line_of_a_firm_costing_by_lot_is_a_lot() -> None:
    """A second delivery of the same printed batch is a second lot."""
    fixture = _shop("LOT2", by_lot=True)

    first = _receive(fixture, "4", batch_number="BN-1")
    second = _receive(fixture, "3", batch_number="BN-1")

    one, two = _batches(fixture.session)
    assert one.lot_reference != two.lot_reference
    for lot, receipt in ((one, first), (two, second)):
        line = fixture.session.scalars(
            select(GoodsReceiptLine).where(
                GoodsReceiptLine.goods_receipt_id == receipt.id
            )
        ).one()
        assert lot.per_purchase_line is True
        assert lot.has_printed_batch is True
        assert lot.batch_number == "BN-1"
        assert lot.source_document_type == "GOODS_RECEIPT"
        assert lot.source_document_id == receipt.id
        assert lot.source_document_line_id == line.id
        assert lot.source_document_number == receipt.grn_number
        assert lot.received_on == date(2026, 8, 5)
        assert line.batch_id == lot.id
    assert _worth(fixture.session, one) == (Decimal("4"), Decimal("400"))
    assert _worth(fixture.session, two) == (Decimal("3"), Decimal("300"))
    item = fixture.session.scalars(select(ProductValuation)).one()
    assert item.costing_method == COSTING_BY_LOT
    assert Decimal(item.quantity_on_hand) == Decimal("7")
    assert Decimal(item.total_value) == Decimal("700")


def test_goods_with_no_printed_batch_still_arrive_in_a_lot() -> None:
    """Our own reference stands in for the batch nobody printed."""
    fixture = _shop("LOT3", by_lot=True, track_batch=False)

    _receive(fixture, "4")

    (lot,) = _batches(fixture.session)
    assert lot.per_purchase_line is True
    assert lot.has_printed_batch is False
    assert lot.batch_number == lot.lot_reference
    stock = fixture.session.scalars(select(InventoryRecord)).one()
    assert stock.batch_id == lot.id
    assert Decimal(stock.current_quantity) == Decimal("4")
    assert _worth(fixture.session, lot) == (Decimal("4"), Decimal("400"))


def test_free_units_arrive_in_the_lines_lot_and_lower_its_cost() -> None:
    """Four paid for and one free are five in the lot, worth what was paid."""
    fixture = _shop("LOT4", by_lot=True)
    # The order has to offer the free unit for a receipt to bring it in.
    fixture.order_line.free_quantity = Decimal("1")
    fixture.session.commit()

    _receive(fixture, "4", batch_number="BN-1", free_quantity="1")

    (lot,) = _batches(fixture.session)
    assert _worth(fixture.session, lot) == (Decimal("5"), Decimal("400"))


def test_cancelling_the_receipt_removes_its_lot() -> None:
    """Goods that never arrived leave no lot behind, and no value."""
    fixture = _shop("LOT5", by_lot=True)
    receipt = _receive(fixture, "4", batch_number="BN-1")

    GoodsReceiptService(fixture.session).cancel_receipt(
        receipt.id,
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
        reason="wrong delivery",
    )

    fixture.session.expire_all()
    assert _batches(fixture.session) == []
    (lot,) = _batches(fixture.session, deleted=True)
    assert _worth(fixture.session, lot) == (Decimal("0"), Decimal("0"))
    item = fixture.session.scalars(select(ProductValuation)).one()
    assert Decimal(item.quantity_on_hand) == Decimal("0")
    assert Decimal(item.total_value) == Decimal("0")


def test_a_receipt_whose_lot_has_moved_cannot_be_cancelled() -> None:
    """A lot that has been sold from is named by the sale; it stays."""
    fixture = _shop("LOT6", by_lot=True)
    receipt = _receive(fixture, "4", batch_number="BN-1")
    (lot,) = _batches(fixture.session)
    InventoryService(fixture.session).record_delivery_note_dispatch(
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
        branch_id=fixture.branch.id,
        warehouse_id=fixture.warehouse.id,
        storage_node_id=None,
        product_id=fixture.product.id,
        reference_number="DN-SOLD",
        transaction_date=date(2026, 8, 6),
        dispatch_quantity=Decimal("1"),
        batch_id=lot.id,
    )
    fixture.session.commit()

    with pytest.raises(ValidationError, match=r"have moved since .*DN-SOLD"):
        GoodsReceiptService(fixture.session).cancel_receipt(
            receipt.id,
            firm_scope=fixture.firm.id,
            actor_id=fixture.actor_id,
            reason="too late",
        )

    fixture.session.rollback()
    assert [row.id for row in _batches(fixture.session)] == [lot.id]


def _opening(session: Session, firm_id: UUID) -> OpeningStockBatch:
    """Enter and post day-one stock: one batch at two costs, and loose rice."""
    warehouse = session.scalars(select(Warehouse).where(Warehouse.code == "MAIN")).one()
    products = {row.code: row for row in session.scalars(select(Product)).all()}
    service = InventoryService(session)
    actor = uuid4()
    document = service.create_opening_stock_batch(
        OpeningStockBatchCreate(
            branch_id=warehouse.branch_id,
            warehouse_id=warehouse.id,
            reference_number="OS-LOTS",
            posting_date=_ON,
            lines=[
                {
                    "product_id": products["SYRUP"].id,
                    "quantity": "10",
                    "unit_cost": "20",
                    "batch_number": "B-MARCH",
                    "expiry_date": "2027-03-31",
                    "mrp": "40.00",
                    "selling_price": "32.00",
                    "purchase_date": "2026-06-10",
                    "supplier_bill_reference": "INV-881",
                },
                {
                    "product_id": products["SYRUP"].id,
                    "quantity": "5",
                    "unit_cost": "25",
                    "batch_number": "B-MARCH",
                    "expiry_date": "2027-03-31",
                    "mrp": "44.00",
                },
                {"product_id": products["RICE"].id, "quantity": "8", "unit_cost": "50"},
            ],
        ),
        firm_id=firm_id,
        actor_id=actor,
    )
    return service.post_opening_stock_batch(
        document.id, firm_scope=firm_id, actor_id=actor
    )


def test_day_one_stock_of_one_batch_at_two_costs_is_two_lots() -> None:
    """Each opening line of a firm costing by lot is a lot with its own figures."""
    session = _factory()()
    firm = _firm(session, warehouses=("MAIN",))
    _by_lot(session, firm.id)

    document = _opening(session, firm.id)

    session.expire_all()
    lots = _batches(session)
    assert len(lots) == 3
    assert {lot.source_document_type for lot in lots} == {"OPENING_STOCK"}
    assert {lot.source_document_id for lot in lots} == {document.id}
    assert {lot.source_document_number for lot in lots} == {"OS-LOTS"}
    assert all(lot.per_purchase_line for lot in lots)
    march = [lot for lot in lots if lot.batch_number == "B-MARCH"]
    assert sorted(
        (lot.received_on, lot.mrp, *_worth(session, lot)) for lot in march
    ) == [
        (date(2026, 6, 10), Decimal("40.00"), Decimal("10"), Decimal("200")),
        (_ON, Decimal("44.00"), Decimal("5"), Decimal("125")),
    ]
    (rice,) = [lot for lot in lots if not lot.has_printed_batch]
    assert rice.batch_number == rice.lot_reference
    assert _worth(session, rice) == (Decimal("8"), Decimal("400"))
    assert {line.batch_id for line in document.lines} == {lot.id for lot in lots}
    kept = sorted(
        (line.supplier_bill_reference or "", line.purchase_date)
        for line in document.lines
    )
    assert kept[-1] == ("INV-881", date(2026, 6, 10))


def test_a_firm_on_average_is_still_refused_the_same_item_twice() -> None:
    """The refusal the dropped key gave is the service's own."""
    session = _factory()()
    firm = _firm(session, warehouses=("MAIN",))

    with pytest.raises(ValidationError, match="Duplicate opening stock lines"):
        _opening(session, firm.id)


def test_stock_bought_after_the_opening_date_is_refused() -> None:
    """Opening stock is what the firm already held that day."""
    session = _factory()()
    firm = _firm(session, warehouses=("MAIN",))
    warehouse = session.scalars(select(Warehouse)).one()
    rice = session.scalars(select(Product).where(Product.code == "RICE")).one()
    service = InventoryService(session)
    actor = uuid4()
    document = service.create_opening_stock_batch(
        OpeningStockBatchCreate(
            branch_id=warehouse.branch_id,
            warehouse_id=warehouse.id,
            reference_number="OS-LATE",
            posting_date=_ON,
            lines=[
                {"product_id": rice.id, "quantity": "2", "purchase_date": "2026-08-02"}
            ],
        ),
        firm_id=firm.id,
        actor_id=actor,
    )

    with pytest.raises(ValidationError, match="after the opening date"):
        service.post_opening_stock_batch(
            document.id, firm_scope=firm.id, actor_id=actor
        )


_HEADINGS = (
    "ProductCode,Warehouse,Quantity,UnitCost,Batch,Expiry,MRP,SellingPrice,"
    "PurchaseDate,SupplierBill"
)


def test_the_file_carries_what_a_lot_carries() -> None:
    """The template names the new columns and a file with them makes lots."""
    session = _factory()()
    firm = _firm(session, warehouses=("MAIN",))
    _by_lot(session, firm.id)
    template = template_csv(session, firm.id)
    for heading in ("MRP", "SellingPrice", "PTR", "PTS", "PurchaseDate"):
        assert heading in template
    assert "SupplierBill" in template

    report = _run(
        session,
        firm.id,
        _csv(
            _HEADINGS,
            "SYRUP,MAIN,10,20,B-MARCH,31/03/2027,40,32,10-06-2026,INV-881",
            "SYRUP,MAIN,5,25,B-MARCH,31/03/2027,44,,,",
        ),
        apply=True,
    )

    assert report.imported, [issue.describe() for issue in report.issues]
    session.expire_all()
    lots = _batches(session)
    assert sorted(
        (lot.received_on, lot.mrp, lot.selling_price, *_worth(session, lot))
        for lot in lots
    ) == [
        (
            date(2026, 6, 10),
            Decimal("40.00"),
            Decimal("32.00"),
            Decimal("10"),
            Decimal("200"),
        ),
        (_ON, Decimal("44.00"), None, Decimal("5"), Decimal("125")),
    ]


def test_a_file_of_a_firm_on_average_keeps_its_rules() -> None:
    """The same batch twice is refused by row, and so is a late purchase date."""
    session = _factory()()
    firm = _firm(session, warehouses=("MAIN",))

    report = _run(
        session,
        firm.id,
        _csv(
            _HEADINGS,
            "SYRUP,MAIN,10,20,B-MARCH,31/03/2027,40,32,10-06-2026,INV-881",
            "SYRUP,MAIN,5,25,B-MARCH,31/03/2027,44,,,",
            "RICE,MAIN,5,25,,,,,02-08-2026,",
        ),
        apply=True,
    )

    assert not report.imported
    told = [issue.describe() for issue in report.issues]
    assert any("appears again" in line for line in told), told
    assert any("after the opening date" in line for line in told), told
    assert _batches(session) == []
