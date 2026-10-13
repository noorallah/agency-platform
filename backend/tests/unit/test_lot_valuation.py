"""Stock valued lot by lot (L2 step 2).

`docs/design/LOT_COST_DESIGN.md`, sections 1 and 4.1. An item whose valuation
is stamped ``BY_LOT`` takes each movement's value from the lot it names; every
other item is valued at its moving average exactly as before. Nothing but
these tests stamps an item yet: the switch-over is a later step.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.batch_serial.models import BatchRecord
from app.branches.models import Warehouse
from app.firms.models import Firm
from app.inventory.models import (
    BatchValuation,
    InventoryTransaction,
    ProductValuation,
    StockLedgerEntry,
)
from app.inventory.services import InventoryService
from app.inventory.services.inventory_service import COSTING_BY_LOT
from app.products.models import Product
from tests.unit.test_opening_stock_import_file import _factory, _firm

_ACTOR = uuid4()
_PAISA = Decimal("0.01")
#: 100 at 42.00 less 5% with 10 free: 3,990.00 over 110 pieces.
_LOT_B_COST = str(Decimal("3990") / Decimal("110"))


class _Shop:
    """One firm, one warehouse and one item, with the movements a test stages."""

    def __init__(self, *, by_lot: bool) -> None:
        """Open the firm and, when asked, stamp the item as costed by lot."""
        self.session: Session = _factory()()
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
        self.item = self.stock.valuation_for(
            firm_scope=self.firm.id, product_id=product.id
        )
        if by_lot:
            self.item.costing_method = COSTING_BY_LOT
        self.session.flush()

    def lot(self, number: str) -> UUID:
        """Add one lot of the item and return its id."""
        row = BatchRecord(
            firm_id=self.firm.id,
            product_id=self.product.id,
            batch_number=number,
            lot_reference=f"L-{number}",
            per_purchase_line=True,
        )
        self.session.add(row)
        self.session.flush()
        return row.id

    def receive(
        self, lot: UUID | None, quantity: str, cost: str, on: date
    ) -> InventoryTransaction:
        """Bring goods into a lot at a cost per unit."""
        return self.stock.record_goods_receipt(
            firm_scope=self.firm.id,
            actor_id=_ACTOR,
            branch_id=self.warehouse.branch_id,
            warehouse_id=self.warehouse.id,
            storage_node_id=None,
            product_id=self.product.id,
            reference_number=f"GRN-{uuid4().hex[:8]}",
            transaction_date=on,
            total_quantity=Decimal(quantity),
            unit_cost=Decimal(cost),
            batch_id=lot,
        )

    def dispatch(self, lot: UUID | None, quantity: str, on: date) -> Decimal:
        """Send goods out of a lot and return what the movement cost."""
        movement = self.dispatch_movement(lot, quantity, on)
        return self.cost_of(movement)

    def dispatch_movement(
        self, lot: UUID | None, quantity: str, on: date
    ) -> InventoryTransaction:
        """Send goods out of a lot and return the movement."""
        return self.stock.record_delivery_note_dispatch(
            firm_scope=self.firm.id,
            actor_id=_ACTOR,
            branch_id=self.warehouse.branch_id,
            warehouse_id=self.warehouse.id,
            storage_node_id=None,
            product_id=self.product.id,
            reference_number=f"DN-{uuid4().hex[:8]}",
            transaction_date=on,
            dispatch_quantity=Decimal(quantity),
            batch_id=lot,
        )

    def take_back(self, lot: UUID, quantity: str, on: date) -> Decimal:
        """Take a customer's return into a lot and return its value."""
        movement = self.stock.record_sales_return(
            firm_scope=self.firm.id,
            actor_id=_ACTOR,
            branch_id=self.warehouse.branch_id,
            warehouse_id=self.warehouse.id,
            storage_node_id=None,
            product_id=self.product.id,
            reference_number=f"SR-{uuid4().hex[:8]}",
            transaction_date=on,
            return_quantity=Decimal(quantity),
            restock_quantity=Decimal(quantity),
            batch_id=lot,
        )
        return self.cost_of(movement)

    def reverse(self, movement: InventoryTransaction) -> Decimal:
        """Reverse a movement and return the value the reversal carried."""
        mirror = self.stock.reverse_transaction(
            movement.id, firm_scope=self.firm.id, actor_id=_ACTOR
        )
        return self.cost_of(mirror)

    def cost_of(self, movement: InventoryTransaction) -> Decimal:
        """Return the value written on a movement's stock ledger row."""
        self.session.flush()
        cost = self.session.scalar(
            select(StockLedgerEntry.total_cost).where(
                StockLedgerEntry.transaction_id == movement.id
            )
        )
        assert cost is not None
        return Decimal(str(cost))

    def worth(self, lot: UUID) -> tuple[Decimal, Decimal]:
        """Return a lot's quantity and its value to the paisa."""
        row = self.session.scalar(
            select(BatchValuation).where(BatchValuation.batch_id == lot)
        )
        assert row is not None
        return (
            Decimal(str(row.quantity_on_hand)),
            Decimal(str(row.total_value)).quantize(_PAISA),
        )

    def item_worth(self) -> tuple[Decimal, Decimal]:
        """Return the item's quantity and its value to the paisa."""
        self.session.flush()
        row = self.session.scalar(
            select(ProductValuation).where(
                ProductValuation.product_id == self.product.id
            )
        )
        assert row is not None
        return (
            Decimal(str(row.quantity_on_hand)),
            Decimal(str(row.total_value)).quantize(_PAISA),
        )

    def lot_rows(self) -> int:
        """Return how many lots of the firm carry a valuation."""
        self.session.flush()
        return len(
            self.session.scalars(
                select(BatchValuation).where(BatchValuation.firm_id == self.firm.id)
            ).all()
        )


def _paisa(value: Decimal) -> Decimal:
    """Round a stored value to the paisa, as the books do."""
    return value.quantize(_PAISA)


def test_the_worked_example_of_the_design_note_to_the_paisa() -> None:
    """Two purchases, one sale across both lots, one return: section 1."""
    shop = _Shop(by_lot=True)
    lot_a = shop.lot("A")
    lot_b = shop.lot("B")

    # 1 Oct: 100 at 40.00.
    shop.receive(lot_a, "100", "40", date(2026, 10, 1))
    assert shop.worth(lot_a) == (Decimal("100"), Decimal("4000.00"))
    # 10 Oct: 100 at 42.00 less 5%, 10 free: 3,990.00 over 110 pieces.
    shop.receive(lot_b, "110", _LOT_B_COST, date(2026, 10, 10))
    assert shop.worth(lot_b) == (Decimal("110"), Decimal("3990.00"))
    assert shop.item_worth() == (Decimal("210"), Decimal("7990.00"))

    # 15 Oct: 150 sold, 100 from lot A and 50 from lot B.
    from_a = shop.dispatch(lot_a, "100", date(2026, 10, 15))
    from_b = shop.dispatch(lot_b, "50", date(2026, 10, 15))
    assert _paisa(from_a) == Decimal("4000.00")
    assert _paisa(from_b) == Decimal("1813.64")
    assert _paisa(from_a + from_b) == Decimal("5813.64")
    assert shop.worth(lot_a) == (Decimal("0"), Decimal("0.00"))
    assert shop.worth(lot_b) == (Decimal("60"), Decimal("2176.36"))
    assert shop.item_worth() == (Decimal("60"), Decimal("2176.36"))

    # 20 Oct: 10 of lot B come back, at the cost they left with.
    back = shop.take_back(lot_b, "10", date(2026, 10, 20))
    assert _paisa(back) == Decimal("362.73")
    assert shop.worth(lot_b) == (Decimal("70"), Decimal("2539.09"))
    assert shop.item_worth() == (Decimal("70"), Decimal("2539.09"))


def test_an_item_on_average_is_valued_as_before_and_makes_no_lot() -> None:
    """The same goods on today's method: one average, 5,707.14 of cost."""
    shop = _Shop(by_lot=False)
    lot_a = shop.lot("A")
    lot_b = shop.lot("B")
    shop.receive(lot_a, "100", "40", date(2026, 10, 1))
    shop.receive(lot_b, "110", _LOT_B_COST, date(2026, 10, 10))

    from_a = shop.dispatch(lot_a, "100", date(2026, 10, 15))
    from_b = shop.dispatch(lot_b, "50", date(2026, 10, 15))

    assert _paisa(from_a + from_b) == Decimal("5707.14")
    assert shop.item_worth() == (Decimal("60"), Decimal("2282.86"))
    assert shop.lot_rows() == 0


def test_a_lot_closes_at_exactly_zero() -> None:
    """The issue that empties a lot takes whatever is left in it."""
    shop = _Shop(by_lot=True)
    lot = shop.lot("A")
    # 10.00 over 3 pieces: 3.333333 each, which no two decimals can hold.
    shop.receive(lot, "3", str(Decimal("10") / Decimal("3")), date(2026, 10, 1))

    first = shop.dispatch(lot, "1", date(2026, 10, 2))
    second = shop.dispatch(lot, "1", date(2026, 10, 3))
    last = shop.dispatch(lot, "1", date(2026, 10, 4))

    assert first + second + last == Decimal("10.0000")
    assert shop.worth(lot) == (Decimal("0"), Decimal("0.00"))
    assert shop.item_worth() == (Decimal("0"), Decimal("0.00"))


def test_a_cancelled_dispatch_puts_back_the_value_it_took() -> None:
    """A reversal carries its original's value, not the lot's cost today."""
    shop = _Shop(by_lot=True)
    lot = shop.lot("A")
    shop.receive(lot, "100", "40", date(2026, 10, 1))
    sold = shop.dispatch_movement(lot, "60", date(2026, 10, 2))
    assert shop.cost_of(sold) == Decimal("2400.0000")
    # More of the same lot arrives dearer, so its cost is no longer 40.00.
    shop.receive(lot, "40", "50", date(2026, 10, 3))
    assert shop.worth(lot) == (Decimal("80"), Decimal("3600.00"))

    put_back = shop.reverse(sold)

    assert put_back == Decimal("2400.0000")
    assert shop.worth(lot) == (Decimal("140"), Decimal("6000.00"))
    assert shop.item_worth() == (Decimal("140"), Decimal("6000.00"))


def test_a_cancelled_receipt_takes_out_the_value_it_brought() -> None:
    """Cancelling one of two deliveries into a lot leaves the other's cost."""
    shop = _Shop(by_lot=True)
    lot = shop.lot("A")
    first = shop.receive(lot, "100", "40", date(2026, 10, 1))
    shop.receive(lot, "100", "50", date(2026, 10, 2))
    assert shop.worth(lot) == (Decimal("200"), Decimal("9000.00"))

    taken = shop.reverse(first)

    # 4,000.00 goes, not 100 at the blended 45.00.
    assert taken == Decimal("4000.0000")
    assert shop.worth(lot) == (Decimal("100"), Decimal("5000.00"))
    # What is left is worth 50.00 each, and leaves at that.
    assert shop.dispatch(lot, "10", date(2026, 10, 3)) == Decimal("500.0000")


def test_the_item_is_always_worth_the_sum_of_its_lots() -> None:
    """The item's own figure is kept, and never parts from the lots."""
    shop = _Shop(by_lot=True)
    lot_a = shop.lot("A")
    lot_b = shop.lot("B")
    shop.receive(lot_a, "7", "13.37", date(2026, 10, 1))
    shop.receive(lot_b, "9", str(Decimal("100") / Decimal("9")), date(2026, 10, 2))
    shop.dispatch(lot_a, "3", date(2026, 10, 3))
    shop.dispatch(lot_b, "4", date(2026, 10, 3))
    shop.take_back(lot_b, "2", date(2026, 10, 4))
    shop.dispatch(lot_a, "4", date(2026, 10, 5))

    quantity_a, value_a = shop.worth(lot_a)
    quantity_b, value_b = shop.worth(lot_b)

    assert shop.item_worth() == (quantity_a + quantity_b, value_a + value_b)
    assert (quantity_a, value_a) == (Decimal("0"), Decimal("0.00"))


def test_goods_with_no_lot_named_still_move_at_the_average() -> None:
    """Until every stock row names a lot, a row without one is not stranded."""
    shop = _Shop(by_lot=True)
    shop.receive(None, "10", "20", date(2026, 10, 1))

    cost = shop.dispatch(None, "4", date(2026, 10, 2))

    assert cost == Decimal("80.0000")
    assert shop.item_worth() == (Decimal("6"), Decimal("120.00"))
    assert shop.lot_rows() == 0
