"""Choosing the lot a sale takes (L2 step 4).

`docs/design/LOT_COST_DESIGN.md`, section 3.4. For a firm costing by lot the
order is nearest expiry first, then oldest received, then our reference, so
goods with no printed batch leave first in, first out. The picker route gives
one row per lot in that order, groups the lots that agree on batch, expiry,
MRP and selling prices, and shows a lot's cost only to somebody allowed to
see cost. A firm on Average is untouched.
"""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.batch_serial.api.router import batch_availability
from app.batch_serial.models import BatchRecord
from app.batch_serial.schemas.batch_serial import BatchAvailability
from app.batch_serial.services import BatchSerialService
from app.branches.models import Warehouse
from app.firms.models import Firm
from app.inventory.models import StockLotSettings
from app.inventory.services import InventoryService
from app.inventory.services.inventory_service import COSTING_BY_LOT
from app.inventory.services.lots import FIRM_BY_LOT
from app.products.models import Product
from tests.unit.test_opening_stock_import_file import _factory, _firm

_ACTOR = uuid4()
_SALE_DAY = date(2026, 10, 14)


class _Shop:
    """One firm, one warehouse and one item, by lot or on Average."""

    def __init__(self, *, by_lot: bool, session: Session | None = None) -> None:
        """Open the firm and, when asked, put it and the item on By lot.

        ``session`` is a PostgreSQL store's, for the integration suite.
        """
        self.session: Session = session or _factory()()
        self.firm: Firm = _firm(self.session, warehouses=("MAIN",))
        warehouse = self.session.scalar(
            select(Warehouse).where(Warehouse.firm_id == self.firm.id)
        )
        product = self.session.scalar(
            select(Product).where(
                Product.firm_id == self.firm.id, Product.code == "SYRUP"
            )
        )
        assert warehouse is not None
        assert product is not None
        self.warehouse = warehouse
        self.product = product
        self.stock = InventoryService(self.session)
        if by_lot:
            self.session.add(
                StockLotSettings(firm_id=self.firm.id, costing_method=FIRM_BY_LOT)
            )
            item = self.stock.valuation_for(
                firm_scope=self.firm.id, product_id=product.id
            )
            item.costing_method = COSTING_BY_LOT
        self.session.flush()

    def lot(
        self,
        reference: str,
        *,
        received_on: date | None,
        cost: str = "10",
        number: str | None = None,
        expiry: date | None = None,
        mrp: str | None = None,
    ) -> UUID:
        """Add a lot holding ten units and return its id."""
        row = BatchRecord(
            firm_id=self.firm.id,
            product_id=self.product.id,
            batch_number=number or reference,
            has_printed_batch=number is not None,
            lot_reference=reference,
            per_purchase_line=True,
            received_on=received_on,
            expiry_date=expiry,
            mrp=Decimal(mrp) if mrp else None,
        )
        self.session.add(row)
        self.session.flush()
        self.stock.record_goods_receipt(
            firm_scope=self.firm.id,
            actor_id=_ACTOR,
            branch_id=self.warehouse.branch_id,
            warehouse_id=self.warehouse.id,
            storage_node_id=None,
            product_id=self.product.id,
            reference_number=f"GRN-{uuid4().hex[:8]}",
            transaction_date=received_on or date(2026, 1, 1),
            total_quantity=Decimal("10"),
            unit_cost=Decimal(cost),
            batch_id=row.id,
        )
        return row.id

    def split(self, quantity: str) -> list[tuple[UUID | None, Decimal]]:
        """Return the lots dispatch would draw, nobody choosing."""
        return self.stock.allocate_for_dispatch(
            firm_scope=self.firm.id,
            branch_id=self.warehouse.branch_id,
            warehouse_id=self.warehouse.id,
            storage_node_id=None,
            product_id=self.product.id,
            quantity=Decimal(quantity),
            as_of=_SALE_DAY,
        )

    def picker(
        self, quantity: str = "0", *, show_cost: bool = False
    ) -> list[BatchAvailability]:
        """Return the picker's rows for the item."""
        return BatchSerialService(self.session).batch_availability(
            firm_scope=self.firm.id,
            product_id=self.product.id,
            warehouse_id=self.warehouse.id,
            as_of=_SALE_DAY,
            quantity=Decimal(quantity),
            show_cost=show_cost,
        )


def test_lots_with_no_batch_leave_oldest_received_first() -> None:
    """Goods with no printed batch go first in, first out, whatever was added last."""
    shop = _Shop(by_lot=True)
    newer = shop.lot("LOT-0002", received_on=date(2026, 9, 1))
    older = shop.lot("LOT-0003", received_on=date(2026, 8, 1))
    split = shop.split("15")
    assert [(lot, qty) for lot, qty in split] == [
        (older, Decimal("10")),
        (newer, Decimal("5")),
    ]
    rows = shop.picker("15")
    assert [row.batch_id for row in rows] == [older, newer]
    assert [row.fefo for row in rows] == [Decimal("10"), Decimal("5")]
    assert all(row.has_printed_batch is False for row in rows)


def test_nearest_expiry_still_comes_before_the_oldest_lot() -> None:
    """Expiry ranks first; received date only breaks a tie, our reference last."""
    shop = _Shop(by_lot=True)
    old_long = shop.lot(
        "LOT-0001", received_on=date(2026, 1, 1), number="B1", expiry=date(2028, 1, 1)
    )
    new_short = shop.lot(
        "LOT-0002", received_on=date(2026, 9, 1), number="B2", expiry=date(2027, 1, 1)
    )
    same_day_b = shop.lot(
        "LOT-0009", received_on=date(2026, 9, 1), number="B3", expiry=date(2027, 6, 1)
    )
    same_day_a = shop.lot(
        "LOT-0005", received_on=date(2026, 9, 1), number="B4", expiry=date(2027, 6, 1)
    )
    undated = shop.lot("LOT-0004", received_on=None, number="B5", expiry=None)
    dated = shop.lot("LOT-0006", received_on=date(2026, 2, 1), number="B6")
    assert [lot for lot, _ in shop.split("60")] == [
        new_short,
        same_day_a,
        same_day_b,
        old_long,
        dated,
        undated,
    ]


def test_lots_that_agree_share_a_picker_row_and_cost_needs_the_right() -> None:
    """Same batch, expiry and prices are one group; cost shows only when allowed."""
    shop = _Shop(by_lot=True)
    first = shop.lot(
        "LOT-0001", received_on=date(2026, 8, 1), number="B1", mrp="50", cost="12"
    )
    second = shop.lot(
        "LOT-0002", received_on=date(2026, 9, 1), number="B1", mrp="50", cost="14"
    )
    dearer = shop.lot(
        "LOT-0003", received_on=date(2026, 9, 2), number="B1", mrp="55", cost="15"
    )
    rows = {row.batch_id: row for row in shop.picker()}
    assert rows[first].pick_group == rows[second].pick_group
    assert rows[dearer].pick_group != rows[first].pick_group
    assert rows[first].lot_reference == "LOT-0001"
    assert rows[first].received_on == date(2026, 8, 1)
    assert all(row.unit_cost is None for row in rows.values())
    costed = {row.batch_id: row.unit_cost for row in shop.picker(show_cost=True)}
    assert costed == {
        first: Decimal("12"),
        second: Decimal("14"),
        dearer: Decimal("15"),
    }


def test_a_firm_on_average_gets_no_groups_and_no_cost() -> None:
    """Average is untouched: no group key, no lot cost even to a cost viewer."""
    shop = _Shop(by_lot=False)
    shop.lot("LOT-0001", received_on=date(2026, 8, 1), number="B1")
    rows = shop.picker(show_cost=True)
    assert [(row.pick_group, row.unit_cost) for row in rows] == [(None, None)]


def test_the_route_shows_cost_only_to_a_cost_viewer() -> None:
    """The picker route asks for ``PRODUCT_VIEW_COST_PRICE`` before it shows cost."""
    shop = _Shop(by_lot=True)
    shop.lot("LOT-0001", received_on=date(2026, 8, 1), cost="12")

    def costs(*held: str) -> list[Decimal | None]:
        """Return the unit costs the route answers to a holder of these codes."""
        principal = SimpleNamespace(has_permission=lambda code: code in held)
        rows = batch_availability(
            scope=SimpleNamespace(  # type: ignore[arg-type]
                firm_id=shop.firm.id, principal=principal
            ),
            product_id=shop.product.id,
            warehouse_id=shop.warehouse.id,
            storage_node_id=None,
            as_of=_SALE_DAY,
            quantity=Decimal("0"),
            sales_order_line_id=None,
            near_expiry_days=None,
            customer_id=None,
            db=shop.session,
        ).data
        assert rows is not None
        return [row.unit_cost for row in rows]

    assert costs("SALES_VIEW") == [None]
    assert costs("SALES_VIEW", "PRODUCT_VIEW_COST_PRICE") == [Decimal("12")]
