"""A line sold by the box is priced, counted and judged as a box.

The second live check of pricing (2026-10-06) sold 2 BOX of a product kept in
pieces, 12 to a box, at 100.00 a piece:

- D-PRC-25: with no price typed the line was charged 100.00 a box -- 236.00
  with tax for 24 pieces. The blank-price fill took the ranking's price, which
  is per stock unit, without converting it to the line's unit.
- D-PRC-26: with the box named and the stock unit left off, the line read a
  quantity of 2 at a factor of 1 while 24 left the shelf, because the order
  converted only when both units were sent and the reservation asked the
  product.

(D-PRC-24, the discount limit on the same line, is in
``test_discount_limit_judges_the_price.py``.)

Every case runs on a request-shaped session (autoflush off).
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.delivery_note.models import DeliveryNoteLine
from app.delivery_note.schemas import DeliveryNoteCreate
from app.delivery_note.services.delivery_note_service import DeliveryNoteService
from app.inventory.models import InventoryRecord
from app.pricing.models import PriceLevel, ProductPriceLevel
from app.purchase.models import PurchaseOrderLine
from app.purchase.schemas import PurchaseOrderCreate
from app.purchase.services import PurchaseService
from app.quotation.models import SalesQuotationLine
from app.quotation.schemas import QuotationCreate
from app.quotation.services.quotation_service import QuotationService
from app.sales_invoice.models import SalesInvoiceLine
from app.sales_invoice.schemas import SalesInvoiceCreate
from app.sales_invoice.services import SalesInvoiceService
from app.sales_order.models import SalesOrder, SalesOrderLine
from app.sales_order.schemas import SalesOrderCreate
from app.sales_order.services.sales_order_service import SalesOrderService
from app.uom.models import ConversionRule, Uom
from tests.unit.test_purchase_management import _vendor
from tests.unit.test_sales_chain_synthesis import _Firm, _request_session

D = Decimal
DAY = date(2026, 8, 4)


def box_of_twelve(session: Session, setup: _Firm) -> tuple[UUID, UUID, UUID]:
    """Keep the firm's product in pieces at 100.00, 12 to a box.

    Returns the piece, the box, and a carton nothing converts.
    """
    piece = Uom(code="PIECE", name="Piece", dimension="COUNT", status="ACTIVE")
    box = Uom(
        code="BOX",
        name="Box",
        dimension="COUNT",
        status="ACTIVE",
        is_decimal_allowed=False,
    )
    carton = Uom(code="CARTON", name="Carton", dimension="COUNT", status="ACTIVE")
    session.add_all([piece, box, carton])
    session.flush()
    setup.product.base_uom_id = piece.id
    setup.product.inventory_uom_id = piece.id
    setup.product.selling_price = D("100")
    setup.product.purchase_price = D("60")
    session.add(
        ConversionRule(
            firm_id=setup.firm.id,
            product_id=setup.product.id,
            from_uom_id=box.id,
            to_uom_id=piece.id,
            conversion_factor=D("12"),
            rounding_mode="HALF_UP",
            precision_scale=4,
            effective_from=date(2026, 4, 1),
            version_number=1,
        )
    )
    session.commit()
    return piece.id, box.id, carton.id


class _Shop:
    """A firm selling a product kept in pieces, by the box of 12."""

    def __init__(self, *, counter: bool = False) -> None:
        """Build the firm; ``counter`` types only the bill."""
        self.session: Session = _request_session()
        self.setup = _Firm(self.session)
        if counter:
            self.setup.stages(quotation=False, sales_order=False, delivery_note=False)
        self.piece, self.box, self.carton = box_of_twelve(self.session, self.setup)
        self.actor = uuid4()
        self.orders = SalesOrderService(self.session)

    @property
    def firm_id(self) -> UUID:
        """Return the firm."""
        return self.setup.firm.id

    def order(self, **line: object) -> SalesOrder:
        """Save a draft order of 2 of the product, with what the line names."""
        return self.orders.create_order(
            SalesOrderCreate.model_validate(
                {
                    "customer_id": self.setup.customer.id,
                    "branch_id": self.setup.branch.id,
                    "warehouse_id": self.setup.warehouse.id,
                    "order_date": DAY,
                    "lines": [
                        {
                            "line_number": 1,
                            "product_id": self.setup.product.id,
                            "quantity": "2",
                        }
                        | line
                    ],
                }
            ),
            firm_id=self.firm_id,
            actor_id=self.actor,
        )

    def line(self, order: SalesOrder) -> SalesOrderLine:
        """Return the order's one line, as stored."""
        self.session.expire_all()
        return self.session.scalars(
            select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order.id)
        ).one()

    def reserved(self) -> Decimal:
        """Return how much of the product the warehouse holds reserved."""
        return D(
            str(
                self.session.scalar(
                    select(
                        func.coalesce(func.sum(InventoryRecord.reserved_quantity), 0)
                    ).where(InventoryRecord.product_id == self.setup.product.id)
                )
            )
        )


def test_a_box_with_no_price_typed_is_charged_twelve_pieces() -> None:
    """D-PRC-25: 2 BOX, price blank, is 2,400.00 before tax, not 200.00."""
    shop = _Shop()

    order = shop.order(sales_uom_id=shop.box, inventory_uom_id=shop.piece)

    line = shop.line(order)
    assert line.unit_price == D("1200.0000")
    assert line.gross_amount == D("2400.0000")
    assert order.subtotal == D("2400.0000")
    assert (line.conversion_factor, line.base_quantity) == (D("12"), D("24.0000"))


def test_a_price_typed_on_a_box_line_is_the_price_of_a_box() -> None:
    """Typed, 600.00 is 600.00 a box: only a blank price is converted."""
    shop = _Shop()

    line = shop.line(
        shop.order(sales_uom_id=shop.box, inventory_uom_id=shop.piece, unit_price="600")
    )

    assert (line.unit_price, line.gross_amount) == (D("600.0000"), D("1200.0000"))


def test_a_line_in_the_stock_unit_is_priced_as_before() -> None:
    """24 PIECE, and 24 with no unit named, are 100.00 each."""
    shop = _Shop()

    named = shop.line(shop.order(quantity="24", sales_uom_id=shop.piece))
    bare = shop.line(shop.order(quantity="24"))

    for line in (named, bare):
        assert (line.unit_price, line.gross_amount) == (D("100.0000"), D("2400.0000"))
        assert (line.conversion_factor, line.base_quantity) == (D("1"), D("24.0000"))


def test_a_box_line_without_the_stock_unit_still_counts_24() -> None:
    """D-PRC-26: BOX named and no stock unit read 2 where 24 were reserved."""
    shop = _Shop()

    order = shop.order(sales_uom_id=shop.box, unit_price="600")

    line = shop.line(order)
    assert line.inventory_uom_id == shop.piece
    assert line.conversion_factor == D("12")
    assert (line.base_quantity, line.reservable_quantity) == (
        D("24.0000"),
        D("24.0000"),
    )
    # The line and the shelf agree on what the approval holds.
    shop.orders.approve_order(order.id, firm_scope=shop.firm_id, actor_id=shop.actor)
    assert shop.line(order).reserved_quantity == D("24.0000")
    assert shop.reserved() == D("24.0000")
    # With no price either, the box is still twelve pieces' worth.
    blank = shop.line(shop.order(sales_uom_id=shop.box))
    assert (blank.unit_price, blank.gross_amount) == (D("1200.0000"), D("2400.0000"))


def test_the_products_stock_unit_wins_over_the_one_the_line_sent() -> None:
    """A line naming BOX and BOX as its stock unit still converts to pieces."""
    shop = _Shop()

    line = shop.line(shop.order(sales_uom_id=shop.box, inventory_uom_id=shop.box))

    assert line.inventory_uom_id == shop.piece
    assert (line.conversion_factor, line.base_quantity) == (D("12"), D("24.0000"))


@pytest.mark.parametrize("price", [None, "600"])
def test_a_unit_no_rule_converts_is_refused_by_name(price: str | None) -> None:
    """A carton with no rule is refused, never counted at a factor of 1."""
    shop = _Shop()
    typed = {} if price is None else {"unit_price": price}

    with pytest.raises(ValidationError) as refused:
        shop.order(sales_uom_id=shop.carton, **typed)

    assert str(refused.value.message) == (
        "SKU-001: no active conversion rule converts CARTON to PIECE. Add one "
        "under Units -> Conversion Rules, or enter the quantity in PIECE."
    )


def test_a_customers_price_level_is_converted_to_the_box_too() -> None:
    """On a level at 90.00 a piece, a box with no price typed is 1,080.00."""
    shop = _Shop()
    level = PriceLevel(firm_id=shop.firm_id, code="WHOLESALE", name="Wholesale")
    shop.session.add(level)
    shop.session.flush()
    shop.session.add(
        ProductPriceLevel(
            firm_id=shop.firm_id,
            price_level_id=level.id,
            product_id=shop.setup.product.id,
            rate=D("90"),
        )
    )
    shop.setup.customer.price_level_id = level.id
    shop.session.commit()

    line = shop.line(shop.order(sales_uom_id=shop.box))

    assert (line.unit_price, line.gross_amount) == (D("1080.0000"), D("2160.0000"))


def test_a_quotation_by_the_box_with_no_price_quotes_a_box() -> None:
    """The same fill on a quotation: 2 BOX is quoted 2,400.00."""
    shop = _Shop()

    quote = QuotationService(shop.session).create_quotation(
        QuotationCreate.model_validate(
            {
                "customer_id": shop.setup.customer.id,
                "branch_id": shop.setup.branch.id,
                "warehouse_id": shop.setup.warehouse.id,
                "quotation_date": DAY,
                "valid_until": date(2026, 8, 31),
                "lines": [
                    {
                        "line_number": 1,
                        "product_id": shop.setup.product.id,
                        "quantity": "2",
                        "sales_uom_id": shop.box,
                    }
                ],
            }
        ),
        firm_id=shop.firm_id,
        actor_id=shop.actor,
    )

    line = shop.session.scalars(select(SalesQuotationLine)).one()
    assert quote.subtotal == D("2400.0000")
    assert (line.unit_price, line.gross_amount) == (D("1200.0000"), D("2400.0000"))


def test_the_note_and_the_bill_of_a_box_order_ship_and_charge_24_pieces() -> None:
    """Order 2 BOX blank; the note ships 24 and the bill charges 2,400.00."""
    shop = _Shop()
    order = shop.order(sales_uom_id=shop.box)
    shop.orders.approve_order(order.id, firm_scope=shop.firm_id, actor_id=shop.actor)
    notes = DeliveryNoteService(shop.session)

    note = notes.create_note(
        DeliveryNoteCreate.model_validate(
            {
                "sales_order_id": order.id,
                "delivery_date": DAY,
                "lines": [
                    {
                        "sales_order_line_id": shop.line(order).id,
                        "line_number": 1,
                        "current_delivery_quantity": "2",
                    }
                ],
            }
        ),
        firm_id=shop.firm_id,
        actor_id=shop.actor,
    )
    notes.approve_note(note.id, firm_scope=shop.firm_id, actor_id=shop.actor)
    notes.dispatch_note(note.id, firm_scope=shop.firm_id, actor_id=shop.actor)

    shop.session.expire_all()
    note_line = shop.session.scalars(
        select(DeliveryNoteLine).where(DeliveryNoteLine.delivery_note_id == note.id)
    ).one()
    assert (note_line.unit_price, note_line.delivered_quantity) == (
        D("1200.0000"),
        D("24.0000"),
    )
    assert shop.reserved() == D("0.0000")
    assert shop.orders.get_order(order.id, firm_scope=shop.firm_id).status == (
        "DELIVERED"
    )
    bill = SalesInvoiceService(shop.session).create_invoice(
        SalesInvoiceCreate.model_validate(
            {
                "customer_id": shop.setup.customer.id,
                "invoice_date": DAY,
                "lines": [
                    {
                        "source_document_type": "DELIVERY_NOTE",
                        "source_document_id": note.id,
                        "source_document_line_id": note_line.id,
                        "line_number": 1,
                        "current_invoice_quantity": "2",
                    }
                ],
            }
        ),
        firm_id=shop.firm_id,
        actor_id=shop.actor,
    )
    assert bill.subtotal == D("2400.0000")


def test_a_counter_bill_by_the_box_with_no_price_charges_a_box() -> None:
    """Stages off: 2 BOX typed straight onto a bill is 2,400.00 for 24 pieces."""
    shop = _Shop(counter=True)

    bill = SalesInvoiceService(shop.session).create_invoice(
        SalesInvoiceCreate.model_validate(
            {
                "customer_id": shop.setup.customer.id,
                "invoice_date": DAY,
                "lines": [
                    {
                        "product_id": shop.setup.product.id,
                        "line_number": 1,
                        "current_invoice_quantity": "2",
                        "invoice_uom_id": shop.box,
                    }
                ],
            }
        ),
        firm_id=shop.firm_id,
        actor_id=shop.actor,
    )

    shop.session.expire_all()
    billed = shop.session.scalars(
        select(SalesInvoiceLine).where(SalesInvoiceLine.sales_invoice_id == bill.id)
    ).one()
    assert (billed.unit_price, billed.gross_amount) == (D("1200.0000"), D("2400.0000"))
    hidden = shop.session.scalars(select(SalesOrderLine)).one()
    assert (hidden.conversion_factor, hidden.base_quantity) == (D("12"), D("24.0000"))
    assert shop.reserved() == D("24.0000")


def test_a_purchase_line_by_the_box_with_no_price_costs_twelve_pieces() -> None:
    """The buying twin: 2 BOX at a purchase price of 60.00 a piece is 1,440.00."""
    shop = _Shop()
    vendor = _vendor(shop.session, firm_id=shop.firm_id, actor_id=shop.actor)

    def buy(**line: object) -> PurchaseOrderLine:
        """Raise a purchase order of 2 and return its one line."""
        order = PurchaseService(shop.session).create_order(
            PurchaseOrderCreate.model_validate(
                {
                    "branch_id": shop.setup.branch.id,
                    "warehouse_id": shop.setup.warehouse.id,
                    "vendor_id": vendor.id,
                    "purchase_date": DAY,
                    "lines": [
                        {
                            "product_id": shop.setup.product.id,
                            "ordered_quantity": "2",
                            "warehouse_id": shop.setup.warehouse.id,
                        }
                        | line
                    ],
                }
            ),
            firm_id=shop.firm_id,
            actor_id=shop.actor,
        )
        shop.session.expire_all()
        return shop.session.scalars(
            select(PurchaseOrderLine).where(
                PurchaseOrderLine.purchase_order_id == order.id
            )
        ).one()

    boxed = buy(purchase_uom_id=shop.box, inventory_uom_id=shop.piece)
    assert (boxed.unit_price, boxed.gross_amount) == (D("720.0000"), D("1440.0000"))
    assert boxed.base_quantity == D("24.0000")
    # Typed, the price is the box's; in pieces, the price is a piece's.
    typed = buy(purchase_uom_id=shop.box, inventory_uom_id=shop.piece, unit_price="700")
    assert typed.unit_price == D("700.0000")
    pieces = buy(purchase_uom_id=shop.piece, inventory_uom_id=shop.piece)
    assert (pieces.unit_price, pieces.gross_amount) == (D("60.0000"), D("120.0000"))
