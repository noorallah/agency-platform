"""Selling by lot (L2 step 5).

`docs/design/LOT_COST_DESIGN.md`, section 3.5. Each lot a delivery line takes
keeps the movement that carried it out and what it cost, so a bill line's
cost is its own lots' and not a share of every line of the product on the
note. The challan and the bill print lots that read alike as one row, and our
own lot reference never prints.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.batch_serial.models.batch_serial import BatchRecord
from app.delivery_note.models import DeliveryNoteLine, DeliveryNoteLineBatch
from app.delivery_note.schemas import DeliveryNoteBatchPick
from app.delivery_note.services.challan_print_service import _per_batch
from app.inventory.models import InventoryTransaction, StockLotSettings
from app.inventory.services import InventoryService
from app.inventory.services.inventory_service import COSTING_BY_LOT
from app.inventory.services.lots import FIRM_BY_LOT
from app.sales_invoice.models import SalesInvoiceLine
from app.sales_invoice.schemas import SalesInvoiceCreate, SalesInvoiceLineWrite
from app.sales_invoice.services.invoice_pdf import InvoiceLineBlock
from tests.unit.test_counter_bill_batches import _Counter


class _ByLot(_Counter):
    """The counter firm of the batch tests, its two lots at two costs."""

    def __init__(self, *, by_lot: bool = True) -> None:
        """Add ten of EARLY at 40 and ten of LATE at 36 to the ten of each at 50.

        The parent stocked its ten before the item went by lot, and those wait
        for the switch-over (step 9), so by lot EARLY leaves at 40 a unit and
        LATE at 36; on Average every unit is worth 44.
        """
        super().__init__()
        session: Session = self.session
        stock = InventoryService(session)
        if by_lot:
            session.add(
                StockLotSettings(firm_id=self.firm.id, costing_method=FIRM_BY_LOT)
            )
            item = stock.valuation_for(firm_scope=self.firm.id, product_id=self.drug.id)
            item.costing_method = COSTING_BY_LOT
            session.flush()
        for name, cost in (("EARLY", "40"), ("LATE", "36")):
            stock.record_goods_receipt(
                firm_scope=self.firm.id,
                actor_id=self.actor,
                branch_id=self.branch.id,
                warehouse_id=self.warehouse.id,
                storage_node_id=None,
                product_id=self.drug.id,
                reference_number=f"GRN2-{name}",
                transaction_date=date(2026, 8, 2),
                total_quantity=Decimal("10"),
                unit_cost=Decimal(cost),
                batch_id=self.batches[name].id,
            )
        session.commit()

    def two_lines(self) -> SalesInvoiceCreate:
        """Bill four from EARLY on one line and four from LATE on another."""
        return SalesInvoiceCreate(
            customer_id=self.customer.id,
            invoice_date=date(2026, 8, 4),
            lines=[
                SalesInvoiceLineWrite(
                    product_id=self.drug.id,
                    line_number=number,
                    current_invoice_quantity=Decimal("4"),
                    unit_price=Decimal("100"),
                    batches=[
                        DeliveryNoteBatchPick(
                            batch_id=self.batches[name].id, quantity=Decimal("4")
                        )
                    ],
                )
                for number, name in ((1, "EARLY"), (2, "LATE"))
            ],
        )

    def bill_costs(self, invoice_id: UUID) -> list[Decimal | None]:
        """Return the bill's line costs in line order."""
        return [
            line.cost_amount
            for line in self.session.scalars(
                select(SalesInvoiceLine)
                .where(SalesInvoiceLine.sales_invoice_id == invoice_id)
                .order_by(SalesInvoiceLine.line_number)
            ).all()
        ]

    def approved(self, data: SalesInvoiceCreate) -> UUID:
        """Create and approve a bill, which dispatches its note; return its id."""
        draft = self.bills.create_invoice(
            data, firm_id=self.firm.id, actor_id=self.actor
        )
        self.bills.approve_invoice(
            draft.id, firm_scope=self.firm.id, actor_id=self.actor
        )
        return draft.id


def test_two_lines_of_one_item_from_two_lots_carry_two_costs() -> None:
    """Four from EARLY cost 160 and four from LATE 144, not 304 each."""
    shop = _ByLot()
    invoice_id = shop.approved(shop.two_lines())

    assert shop.bill_costs(invoice_id) == [Decimal("160.0000"), Decimal("144.0000")]
    picks = shop.session.scalars(select(DeliveryNoteLineBatch)).all()
    movements = {
        row.id: row
        for row in shop.session.scalars(
            select(InventoryTransaction).where(
                InventoryTransaction.transaction_type == "DISPATCH"
            )
        ).all()
    }
    assert sorted(pick.cost_amount or 0 for pick in picks) == [
        Decimal("144.0000"),
        Decimal("160.0000"),
    ]
    for pick in picks:
        assert pick.inventory_transaction_id in movements
        assert movements[pick.inventory_transaction_id].batch_id == pick.batch_id


def test_lots_drawn_with_no_choice_keep_their_movement_and_cost() -> None:
    """Four with no batch named leave from EARLY, costed at EARLY's 40."""
    shop = _ByLot()
    invoice_id = shop.approved(shop.bill(None))

    [pick] = shop.session.scalars(select(DeliveryNoteLineBatch)).all()
    assert pick.batch_id == shop.batches["EARLY"].id
    assert pick.cost_amount == Decimal("160.0000")
    assert pick.inventory_transaction_id is not None
    assert shop.bill_costs(invoice_id) == [Decimal("160.0000")]


def test_a_firm_on_average_bills_each_line_its_own_share() -> None:
    """On Average both lines leave at the one average of 44, so 176 each.

    Before step 5 each line read the note's cost by product whole, so two
    lines of one item each took the cost of both.
    """
    shop = _ByLot(by_lot=False)
    invoice_id = shop.approved(shop.two_lines())

    assert shop.bill_costs(invoice_id) == [Decimal("176.0000"), Decimal("176.0000")]


def test_a_pick_with_no_cost_leaves_the_line_to_the_ledger() -> None:
    """A row written before the lots kept their cost reads the old figure."""
    shop = _ByLot()
    shop.approved(shop.bill(None))
    [pick] = shop.session.scalars(select(DeliveryNoteLineBatch)).all()
    pick.cost_amount = None
    shop.session.flush()
    note_line = shop.session.get(DeliveryNoteLine, pick.delivery_note_line_id)
    assert note_line is not None

    costs = shop.bills._dispatch_costs({note_line.delivery_note_id})

    assert costs.by_line == {}
    assert sum(costs.by_product.values()) == Decimal("160.0000")


def _line() -> InvoiceLineBlock:
    """Return a line of six worth 600, to be printed by lot."""
    return InvoiceLineBlock(
        number=1,
        description="Syrup",
        hsn=None,
        quantity=Decimal("6"),
        uom=None,
        rate=Decimal("100"),
        discount=Decimal("0"),
        taxable=Decimal("600.00"),
        total=Decimal("600.00"),
    )


def _lot(number: str, *, printed: bool = True, mrp: str = "120") -> BatchRecord:
    """Return a lot, unsaved, as the print reads it."""
    return BatchRecord(
        batch_number=number,
        lot_reference=uuid4().hex[:12],
        has_printed_batch=printed,
        expiry_date=date(2027, 6, 30),
        mrp=Decimal(mrp),
    )


def test_lots_that_read_alike_print_as_one_row() -> None:
    """Two lots of B1 at one MRP are one row of four; B1 at another MRP is not."""
    rows = _per_batch(
        _line(),
        [
            (_lot("B1"), Decimal("2")),
            (_lot("B1"), Decimal("2")),
            (_lot("B1", mrp="130"), Decimal("2")),
        ],
        Decimal("6"),
    )

    assert [(row.batch, row.mrp, row.quantity) for row in rows] == [
        ("B1", Decimal("120"), Decimal("4.0000")),
        ("B1", Decimal("130"), Decimal("2.0000")),
    ]
    assert sum(row.total for row in rows) == Decimal("600.00")


def test_our_own_lot_reference_never_prints() -> None:
    """Goods with no printed batch print no batch, alone or merged."""
    [alone] = _per_batch(
        _line(), [(_lot("LOT000001", printed=False), Decimal("6"))], Decimal("6")
    )
    assert alone.batch is None

    rows = _per_batch(
        _line(),
        [
            (_lot("LOT000001", printed=False), Decimal("3")),
            (_lot("LOT000002", printed=False), Decimal("3")),
        ],
        Decimal("6"),
    )

    assert [(row.batch, row.quantity) for row in rows] == [(None, Decimal("6"))]
