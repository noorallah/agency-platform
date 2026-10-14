"""Billing without stock on a firm costing by lot (L2 step 7a).

`docs/design/LOT_COST_DESIGN.md`, section 3.7. Refused by default; a firm
may allow it, and then the bill maker is asked and confirms. The units leave
at the last purchase cost and wait in ``lot_shortfalls``. The receipt that
brings their lot covers them at once and the difference is posted on its
date, so the sale ends up costing what its lot cost; a return before then
clears them at the cost used; a year with one waiting cannot be closed.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.batch_serial.models import BatchRecord
from app.batch_serial.services import BatchSerialService
from app.core.exceptions import ValidationError
from app.delivery_note.models import DeliveryNoteLineBatch
from app.finance.models import AccountingPeriod, FinancialYear, JournalEntry
from app.finance.services.document_posting import DocumentPostingService
from app.finance.services.finance_service import FinanceService
from app.goods_receipt.services import GoodsReceiptService
from app.inventory.models import (
    BatchValuation,
    InventoryRecord,
    LotShortfall,
    LotShortfallSettlement,
    ProductValuation,
    StockLotSettings,
)
from app.inventory.services import InventoryService
from app.inventory.services.inventory_service import COSTING_BY_LOT
from app.inventory.services.lot_shortfalls import LotShortfallService
from app.inventory.services.lots import FIRM_BY_LOT, LotSource
from app.products.models import Product
from app.sales_invoice.models import SalesInvoiceLine
from app.sales_invoice.schemas import SalesInvoiceCreate, SalesInvoiceLineWrite
from app.sales_invoice.services.sales_invoice_service import SalesInvoiceService
from app.sales_return.services import SalesReturnService
from tests.unit.test_lot_receiving import _receive, _shop
from tests.unit.test_lot_returns import _returned
from tests.unit.test_sales_chain_synthesis import _Firm, _session_factory

# The receipt fixture types its order number; see conftest (D-CFG-2).
pytestmark = pytest.mark.typed_document_numbers


class _Short(_Firm):
    """A counter firm costing by lot, three units of an item in one lot at 40."""

    def __init__(
        self, *, allow: bool = True, negative: bool = True, by_lot: bool = True
    ) -> None:
        """Set the firm's switch and the item's own, and stock the first lot."""
        super().__init__(_session_factory()())
        self.stages(quotation=False, sales_order=False, delivery_note=False)
        self.actor = uuid4()
        self.session.add(
            StockLotSettings(
                firm_id=self.firm.id,
                costing_method=FIRM_BY_LOT if by_lot else "AVERAGE",
                allow_billing_without_stock=allow,
            )
        )
        self.item = Product(
            firm_id=self.firm.id,
            code="SKU-LOT",
            name="Lot item",
            product_type="STOCK_ITEM",
            status="ACTIVE",
            allow_negative_stock=negative,
        )
        self.session.add(self.item)
        self.session.commit()
        if by_lot:
            stock = InventoryService(self.session)
            valuation = stock.valuation_for(
                firm_scope=self.firm.id, product_id=self.item.id
            )
            valuation.costing_method = COSTING_BY_LOT
            self.session.flush()
        self.first = self.lot_in("3", "40", "GRN-1")
        self.bills = SalesInvoiceService(self.session)

    def lot_in(self, quantity: str, cost: str, number: str) -> BatchRecord:
        """Take goods into a lot of their own, as a receipt does."""
        lot = BatchSerialService(self.session).open_lot(
            firm_scope=self.firm.id,
            actor_id=self.actor,
            product_id=self.item.id,
            source=LotSource(
                document_type="GOODS_RECEIPT",
                document_id=uuid4(),
                line_id=uuid4(),
                document_number=number,
                received_on=date(2026, 8, 2),
            ),
            branch_id=self.branch.id,
            warehouse_id=self.warehouse.id,
        )
        InventoryService(self.session).record_goods_receipt(
            firm_scope=self.firm.id,
            actor_id=self.actor,
            branch_id=self.branch.id,
            warehouse_id=self.warehouse.id,
            storage_node_id=None,
            product_id=self.item.id,
            reference_number=number,
            transaction_date=date(2026, 8, 2),
            total_quantity=Decimal(quantity),
            unit_cost=Decimal(cost),
            batch_id=lot.id,
        )
        self.session.commit()
        return lot

    def bill_of(self, quantity: str) -> UUID:
        """Create a counter bill of the item; return its id, still a draft."""
        draft = self.bills.create_invoice(
            SalesInvoiceCreate(
                customer_id=self.customer.id,
                invoice_date=date(2026, 8, 4),
                lines=[
                    SalesInvoiceLineWrite(
                        product_id=self.item.id,
                        line_number=1,
                        current_invoice_quantity=Decimal(quantity),
                        unit_price=Decimal("100"),
                    )
                ],
            ),
            firm_id=self.firm.id,
            actor_id=self.actor,
        )
        return draft.id

    def sold_short(self) -> SalesInvoiceLine:
        """Bill five, three in the lot and two past it, confirmed."""
        invoice_id = self.bill_of("5")
        self.bills.approve_invoice(
            invoice_id,
            firm_scope=self.firm.id,
            actor_id=self.actor,
            bill_without_stock=True,
        )
        self.session.expire_all()
        return self.session.scalars(
            select(SalesInvoiceLine).where(
                SalesInvoiceLine.sales_invoice_id == invoice_id
            )
        ).one()

    def unlotted(self) -> Decimal:
        """Return what the item's row with no lot holds."""
        row = self.session.scalars(
            select(InventoryRecord).where(
                InventoryRecord.product_id == self.item.id,
                InventoryRecord.batch_id.is_(None),
            )
        ).one()
        return Decimal(row.current_quantity)

    def item_value(self) -> Decimal:
        """Return the item's running value."""
        row = self.session.scalars(
            select(ProductValuation).where(ProductValuation.product_id == self.item.id)
        ).one()
        return Decimal(row.total_value)

    def waiting(self) -> list[tuple[Decimal, Decimal]]:
        """Return each open shortfall's units and cost still waiting."""
        return [
            (item.quantity, item.cost)
            for item in LotShortfallService(self.session).open_shortfalls(self.firm.id)
        ]


def test_a_firm_that_does_not_allow_it_refuses_as_before() -> None:
    """Switch off, item not allowed below zero, or Average: refused by name."""
    for shop in (
        _Short(allow=False),
        _Short(negative=False),
        _Short(by_lot=False),
    ):
        invoice_id = shop.bill_of("5")
        with pytest.raises(ValidationError, match="Insufficient available stock"):
            shop.bills.approve_invoice(
                invoice_id,
                firm_scope=shop.firm.id,
                actor_id=shop.actor,
                bill_without_stock=True,
            )


def test_the_bill_maker_is_asked_before_anything_moves() -> None:
    """Allowed but not confirmed: refused with the question to put."""
    shop = _Short()
    invoice_id = shop.bill_of("5")

    with pytest.raises(ValidationError, match="Bill anyway") as refused:
        shop.bills.approve_invoice(
            invoice_id, firm_scope=shop.firm.id, actor_id=shop.actor
        )

    details = refused.value.details
    assert isinstance(details, dict)
    assert details["confirm"] == "BILL_WITHOUT_STOCK"
    assert Decimal(str(details["short"])) == Decimal("2")


def test_a_confirmed_bill_takes_the_lot_then_the_rest_at_the_last_cost() -> None:
    """Three leave the lot at 40, two leave with no lot at 40 and wait."""
    shop = _Short()
    line = shop.sold_short()

    [row] = shop.session.scalars(select(LotShortfall)).all()
    assert Decimal(row.quantity) == Decimal("2")
    assert Decimal(row.unit_cost) == Decimal("40")
    assert Decimal(row.cost_amount) == Decimal("80")
    assert row.confirmed_by == shop.actor
    assert shop.unlotted() == Decimal("-2")
    assert line.cost_amount == Decimal("200.0000")
    # The Inventory figure is the lots less the units owed to them.
    assert shop.item_value() == Decimal("-80")
    assert shop.waiting() == [(Decimal("2"), Decimal("80"))]


def test_the_lot_that_comes_in_covers_the_sale_at_its_own_cost() -> None:
    """Two covered from a lot at 46: the sale's cost is 212, not 200."""
    shop = _Short()
    shop.sold_short()
    lot = shop.lot_in("10", "46", "GRN-2")

    out_by = LotShortfallService(shop.session).settle_from_lot(
        firm_id=shop.firm.id,
        product_id=shop.item.id,
        lot_id=lot.id,
        lot_place=(shop.branch.id, shop.warehouse.id, None),
        available=Decimal("10"),
        on=date(2026, 8, 6),
        document_id=uuid4(),
        document_line_id=uuid4(),
        document_number="GRN-2",
        actor_id=shop.actor,
    )
    shop.session.commit()

    assert out_by == Decimal("12")
    assert shop.waiting() == []
    assert shop.unlotted() == Decimal("0")
    worth = shop.session.scalars(
        select(BatchValuation).where(BatchValuation.batch_id == lot.id)
    ).one()
    assert Decimal(worth.quantity_on_hand) == Decimal("8")
    assert Decimal(worth.total_value) == Decimal("368")
    assert shop.item_value() == Decimal("368")
    picks = shop.session.scalars(
        select(DeliveryNoteLineBatch).where(DeliveryNoteLineBatch.batch_id == lot.id)
    ).all()
    assert [(Decimal(p.quantity), p.cost_amount) for p in picks] == [
        (Decimal("2"), Decimal("92.0000"))
    ]


def test_a_return_before_the_purchase_clears_the_units_at_the_cost_used() -> None:
    """Two back: the shortfall clears at 80; cancelling the return reopens it."""
    shop = _Short()
    line = shop.sold_short()

    return_id = _returned(shop, line, "2")  # type: ignore[arg-type]

    [cleared] = shop.session.scalars(select(LotShortfallSettlement)).all()
    assert cleared.kind == "RETURNED"
    assert Decimal(cleared.cost_used_amount) == Decimal("80")
    assert shop.waiting() == []
    assert shop.unlotted() == Decimal("0")

    SalesReturnService(shop.session).cancel_return(
        return_id, firm_scope=shop.firm.id, actor_id=shop.actor
    )
    shop.session.expire_all()

    assert shop.waiting() == [(Decimal("2"), Decimal("80"))]
    assert shop.unlotted() == Decimal("-2")
    assert shop.item_value() == Decimal("-80")


def test_a_year_with_a_bill_waiting_for_its_cost_cannot_be_closed() -> None:
    """Every period closed and no draft: still refused, naming the bill."""
    shop = _Short()
    shop.sold_short()
    year = shop.session.scalars(
        select(FinancialYear).where(FinancialYear.firm_id == shop.firm.id)
    ).one()
    for period in shop.session.scalars(select(AccountingPeriod)).all():
        period.status = "CLOSED"
    shop.session.commit()

    with pytest.raises(ValidationError, match="wait"):
        FinanceService(shop.session).close_financial_year(
            year.id, firm_id=shop.firm.id, actor_id=shop.actor
        )


def test_the_report_lists_what_waits_and_hides_the_cost_unless_allowed() -> None:
    """Bills waiting for their cost: one row, its age, cost by permission."""
    shop = _Short()
    shop.sold_short()
    shortfalls = LotShortfallService(shop.session)

    [shown] = shortfalls.report(shop.firm.id, show_cost=True)
    [hidden] = shortfalls.report(shop.firm.id, show_cost=False)

    assert shown.product_code == "SKU-LOT"
    assert shown.quantity_waiting == Decimal("2")
    assert shown.cost_waiting == Decimal("80")
    assert shown.age_days >= 0
    assert hidden.unit_cost is None
    assert hidden.cost_waiting is None


def test_the_goods_receipt_covers_what_waits_and_posts_the_difference() -> None:
    """A receipt at 100 covers two that left at 90: 20 more cost, its date."""
    fixture = _shop("LOT7A", by_lot=True, track_batch=False)
    fixture.product.allow_negative_stock = True
    fixture.session.commit()
    stock = InventoryService(fixture.session)
    stock.valuation_for(
        firm_scope=fixture.firm.id, product_id=fixture.product.id
    ).costing_method = COSTING_BY_LOT
    sale = stock.record_delivery_note_dispatch(
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
        branch_id=fixture.branch.id,
        warehouse_id=fixture.warehouse.id,
        storage_node_id=None,
        product_id=fixture.product.id,
        reference_number="DN-1",
        transaction_date=date(2026, 8, 4),
        dispatch_quantity=Decimal("2"),
        unit_cost=Decimal("90"),
    )
    note_line_id = uuid4()
    LotShortfallService(fixture.session).record(
        firm_id=fixture.firm.id,
        product_id=fixture.product.id,
        place=(fixture.branch.id, fixture.warehouse.id, None),
        note_id=uuid4(),
        note_line_id=note_line_id,
        document_number="DN-1",
        movement=sale,
        sale_date=date(2026, 8, 4),
        unit_cost=Decimal("90"),
        actor_id=fixture.actor_id,
    )
    fixture.session.commit()

    receipt = _receive(fixture, "10")

    assert LotShortfallService(fixture.session).open_shortfalls(fixture.firm.id) == []
    [pick] = fixture.session.scalars(
        select(DeliveryNoteLineBatch).where(
            DeliveryNoteLineBatch.delivery_note_line_id == note_line_id
        )
    ).all()
    assert pick.cost_amount == Decimal("200.0000")
    [correction] = fixture.session.scalars(
        select(JournalEntry).where(
            JournalEntry.reference_number == f"{receipt.grn_number}-LS"
        )
    ).all()
    assert correction.journal_date == receipt.receipt_date
    # The lot has moved, so the receipt can no longer be taken back whole.
    with pytest.raises(ValidationError, match="moved since"):
        GoodsReceiptService(fixture.session).cancel_receipt(
            receipt.id,
            firm_scope=fixture.firm.id,
            actor_id=fixture.actor_id,
            reason="wrong",
        )


def test_no_correction_is_posted_when_the_costs_agree() -> None:
    """A lot at the cost the sale used leaves nothing to post."""
    shop = _Short()
    assert (
        DocumentPostingService(shop.session).post_cost_correction(
            firm_id=shop.firm.id,
            document_id=uuid4(),
            document_number="GRN-0-LS",
            correction_date=date(2026, 8, 6),
            amount=Decimal("0"),
            source_module="goods_receipt",
            actor_id=shop.actor,
        )
        is None
    )
