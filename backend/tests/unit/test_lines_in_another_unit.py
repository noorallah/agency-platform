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

from app.commission.schemas import (
    CommissionBasisEnum,
    CommissionRateTypeEnum,
    CommissionRuleCreate,
)
from app.commission.services.commission_service import CommissionService
from app.core.exceptions import ValidationError
from app.core.utils.quantities import at_quantity_scale, plain_quantity
from app.delivery_note.models import DeliveryNoteLine
from app.delivery_note.schemas import DeliveryNoteCreate
from app.delivery_note.services.delivery_note_service import DeliveryNoteService
from app.identity.models import User, UserFirm
from app.inventory.models import InventoryRecord
from app.pricing.models import (
    PriceLevel,
    PriceList,
    PriceListItem,
    ProductPriceLevel,
)
from app.purchase.models import PurchaseOrderLine
from app.purchase.schemas import PurchaseOrderCreate
from app.purchase.services import PurchaseService
from app.quotation.models import SalesQuotationLine
from app.quotation.schemas import QuotationCreate
from app.quotation.services.quotation_service import QuotationService
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine
from app.sales_invoice.schemas import SalesInvoiceCreate
from app.sales_invoice.services import SalesInvoiceService
from app.sales_invoice.services.gst_sales_register import GstSalesRegisterService
from app.sales_invoice.services.invoice_print_service import (
    SalesInvoicePrintService,
)
from app.sales_order.models import SalesOrder, SalesOrderLine
from app.sales_order.schemas import SalesOrderCreate
from app.sales_order.services.sales_order_service import SalesOrderService
from app.sales_return.models import SalesReturn, SalesReturnLine
from app.sales_return.schemas import SalesReturnCreate
from app.sales_return.services import SalesReturnService
from app.sales_return.services.credit_note_print_service import (
    CreditNotePrintService,
)
from app.uom.models import ConversionRule, Uom
from tests.unit.test_purchase_management import _vendor
from tests.unit.test_sales_chain_synthesis import _Firm, _request_session
from tests.unit.test_sales_order_module import _tax_group

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


def _note_of(shop: _Shop, order: SalesOrder, quantity: str, **line: object) -> UUID:
    """Save a note of the approved order's one line, with what the line names."""
    note = DeliveryNoteService(shop.session).create_note(
        DeliveryNoteCreate.model_validate(
            {
                "sales_order_id": order.id,
                "delivery_date": DAY,
                "lines": [
                    {
                        "sales_order_line_id": shop.line(order).id,
                        "line_number": 1,
                        "current_delivery_quantity": quantity,
                    }
                    | line
                ],
            }
        ),
        firm_id=shop.firm_id,
        actor_id=shop.actor,
    )
    return note.id


def test_a_note_line_in_another_unit_than_its_order_line_is_refused() -> None:
    """D-PRC-47: 24 PIECE against 2 BOX kept the box's price; 2 BOX shipped 24."""
    shop = _Shop()
    by_the_box = shop.order(sales_uom_id=shop.box)
    by_the_piece = shop.order(quantity="24")
    for order in (by_the_box, by_the_piece):
        shop.orders.approve_order(
            order.id, firm_scope=shop.firm_id, actor_id=shop.actor
        )

    with pytest.raises(ValidationError) as boxes:
        _note_of(shop, by_the_box, "24", sales_uom_id=shop.piece)
    assert str(boxes.value) == (
        f"Line 1 is delivered in PIECE where {by_the_box.order_number} orders "
        "it in BOX. Deliver it in the order's unit."
    )
    shop.session.rollback()
    # The order by the piece names no unit: it is in the product's stock unit.
    with pytest.raises(ValidationError) as pieces:
        _note_of(shop, by_the_piece, "2", sales_uom_id=shop.box)
    assert str(pieces.value) == (
        f"Line 1 is delivered in BOX where {by_the_piece.order_number} orders "
        "it in PIECE. Deliver it in the order's unit."
    )
    shop.session.rollback()
    assert shop.session.scalars(select(DeliveryNoteLine)).all() == []


def test_a_note_line_naming_its_order_lines_own_unit_is_unchanged() -> None:
    """BOX against BOX and PIECE against an order in pieces count as before."""
    shop = _Shop()
    by_the_box = shop.order(sales_uom_id=shop.box)
    by_the_piece = shop.order(quantity="24")
    for order in (by_the_box, by_the_piece):
        shop.orders.approve_order(
            order.id, firm_scope=shop.firm_id, actor_id=shop.actor
        )

    _note_of(shop, by_the_box, "2", sales_uom_id=shop.box)
    _note_of(shop, by_the_piece, "24", sales_uom_id=shop.piece)

    shop.session.expire_all()
    assert sorted(
        (row.current_delivery_quantity, row.delivered_quantity, row.unit_price)
        for row in shop.session.scalars(select(DeliveryNoteLine))
    ) == [
        (D("2.0000"), D("24.0000"), D("1200.0000")),
        (D("24.0000"), D("24.0000"), D("100.0000")),
    ]


def test_a_note_line_cannot_count_a_box_order_in_another_stock_unit() -> None:
    """The stock unit is the order line's: BOX sent as it still ships 24."""
    shop = _Shop()
    order = shop.order(sales_uom_id=shop.box)
    shop.orders.approve_order(order.id, firm_scope=shop.firm_id, actor_id=shop.actor)

    _note_of(shop, order, "2", inventory_uom_id=shop.box)

    shop.session.expire_all()
    line = shop.session.scalars(select(DeliveryNoteLine)).one()
    assert (line.inventory_uom_id, line.delivered_quantity) == (
        shop.piece,
        D("24.0000"),
    )


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


def _list_with_a_break_at_twenty(shop: _Shop, *, at: str = "20") -> None:
    """Give the customer a price list: 2% off, 5% off from 20 stock units."""
    price_list = PriceList(
        firm_id=shop.firm_id,
        code="BREAKS",
        name="Breaks",
        customer_id=shop.setup.customer.id,
        effective_from=date(2026, 4, 1),
    )
    shop.session.add(price_list)
    shop.session.flush()
    shop.session.add_all(
        [
            PriceListItem(
                price_list_id=price_list.id,
                firm_id=shop.firm_id,
                product_id=shop.setup.product.id,
                min_quantity=D(quantity),
                discount_percent=D(percent),
            )
            for quantity, percent in (("0", "2"), (at, "5"))
        ]
    )
    shop.session.commit()


def test_a_price_lists_discount_break_counts_the_pieces_in_a_box() -> None:
    """2 BOX of 12 reach the break "from 20"; one box of 12 does not."""
    shop = _Shop()
    _list_with_a_break_at_twenty(shop)

    two = shop.line(shop.order(sales_uom_id=shop.box))
    one = shop.line(shop.order(quantity="1", sales_uom_id=shop.box))
    pieces = shop.line(shop.order(quantity="24"))

    assert (two.discount_percent, two.discount_amount) == (D("5.0000"), D("120.0000"))
    assert (one.discount_percent, one.discount_amount) == (D("2.0000"), D("24.0000"))
    assert pieces.discount_percent == D("5.0000")


def _kept_by_the_box(shop: _Shop) -> None:
    """Turn the product round: kept in BOX at 1,200.00, sold by the PIECE.

    The fourth check's product (D-PRC-52). A piece is a twelfth of a box,
    which the rule's ten places can only write as 0.0833333333.
    """
    product = shop.setup.product
    product.base_uom_id = shop.box
    product.inventory_uom_id = shop.box
    product.selling_price = D("1200")
    box = shop.session.get(Uom, shop.box)
    assert box is not None
    box.is_decimal_allowed = True
    shop.session.add(
        ConversionRule(
            firm_id=shop.firm_id,
            product_id=product.id,
            from_uom_id=shop.piece,
            to_uom_id=shop.box,
            conversion_factor=D("0.0833333333"),
            rounding_mode="HALF_UP",
            precision_scale=4,
            effective_from=date(2026, 4, 1),
            version_number=1,
        )
    )
    shop.session.commit()


def test_pieces_of_a_product_kept_by_the_box_reach_the_break_at_two_boxes() -> None:
    """D-PRC-52: 24 PIECE are 2 boxes, asked as 1.9999999992 and given 2%."""
    shop = _Shop()
    _kept_by_the_box(shop)
    _list_with_a_break_at_twenty(shop, at="2")

    two_boxes = shop.line(shop.order(quantity="24", sales_uom_id=shop.piece))
    one_box = shop.line(shop.order(quantity="12", sales_uom_id=shop.piece))
    by_the_box = shop.line(shop.order(sales_uom_id=shop.box))
    short = shop.line(shop.order(quantity="23", sales_uom_id=shop.piece))

    assert (two_boxes.unit_price, two_boxes.base_quantity) == (
        D("100.0000"),
        D("2.0000"),
    )
    assert (two_boxes.discount_percent, two_boxes.discount_amount) == (
        D("5.0000"),
        D("120.0000"),
    )
    assert by_the_box.discount_amount == D("120.0000")
    assert (one_box.discount_percent, one_box.discount_amount) == (
        D("2.0000"),
        D("24.0000"),
    )
    assert short.discount_percent == D("2.0000")


def test_a_quotation_in_pieces_of_a_boxed_product_takes_the_same_break() -> None:
    """The quotation asks the list the way the order does."""
    shop = _Shop()
    _kept_by_the_box(shop)
    _list_with_a_break_at_twenty(shop, at="2")

    line = _quote(shop, quantity="24", sales_uom_id=shop.piece)

    assert (line.discount_percent, line.discount_amount) == (
        D("5.0000"),
        D("120.0000"),
    )


def test_loose_pieces_of_a_boxed_product_are_charged_as_typed_all_the_way() -> None:
    """7 PIECE at 100.00 is 700.00 on the order, the note and the bill.

    The shelf holds boxes at four places, so 0.5833 of one leaves; the money
    is 7 times the price of a piece and never 0.5833 of a box's.
    """
    shop = _Shop()
    _kept_by_the_box(shop)
    order = shop.order(quantity="7", sales_uom_id=shop.piece)
    stored = shop.line(order)
    assert (stored.unit_price, stored.gross_amount, stored.base_quantity) == (
        D("100.0000"),
        D("700.0000"),
        D("0.5833"),
    )
    shop.orders.approve_order(order.id, firm_scope=shop.firm_id, actor_id=shop.actor)
    notes = DeliveryNoteService(shop.session)

    note_id = _note_of(shop, order, "7")
    notes.approve_note(note_id, firm_scope=shop.firm_id, actor_id=shop.actor)
    notes.dispatch_note(note_id, firm_scope=shop.firm_id, actor_id=shop.actor)

    shop.session.expire_all()
    note_line = shop.session.scalars(
        select(DeliveryNoteLine).where(DeliveryNoteLine.delivery_note_id == note_id)
    ).one()
    assert (
        note_line.current_delivery_quantity,
        note_line.sales_uom_id,
        note_line.unit_price,
        note_line.gross_amount,
        note_line.delivered_quantity,
    ) == (D("7.0000"), shop.piece, D("100.0000"), D("700.0000"), D("0.5833"))
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
                        "source_document_id": note_id,
                        "source_document_line_id": note_line.id,
                        "line_number": 1,
                        "current_invoice_quantity": "7",
                    }
                ],
            }
        ),
        firm_id=shop.firm_id,
        actor_id=shop.actor,
    )
    assert bill.subtotal == D("700.0000")


def _quote(shop: _Shop, **line: object) -> SalesQuotationLine:
    """Quote 2 of the product, with what the line names, and return the line."""
    QuotationService(shop.session).create_quotation(
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
                    }
                    | line
                ],
            }
        ),
        firm_id=shop.firm_id,
        actor_id=shop.actor,
    )
    return shop.session.scalars(select(SalesQuotationLine)).one()


def test_a_quotation_by_the_box_takes_the_same_discount_break() -> None:
    """The quotation the order comes from quotes the 5% the order will give."""
    shop = _Shop()
    _list_with_a_break_at_twenty(shop)

    line = _quote(shop, sales_uom_id=shop.box)

    assert (line.discount_percent, line.discount_amount) == (
        D("5.0000"),
        D("120.0000"),
    )


def test_a_quotation_in_a_unit_no_list_prices_still_converts_nothing() -> None:
    """A typed price in a carton no rule converts is quoted, as before."""
    shop = _Shop()

    line = _quote(shop, sales_uom_id=shop.carton, unit_price="900")

    assert line.gross_amount == D("1800.0000")


def _billed_by_the_box(shop: _Shop) -> SalesInvoice:
    """Order, ship and bill 2 BOX, and return the bill."""
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
    return SalesInvoiceService(shop.session).create_invoice(
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


def test_a_per_unit_commission_pays_for_the_pieces_in_a_box() -> None:
    """2.50 a unit on 2 BOX of 12 is 60.00, as it is on 24 pieces."""
    shop = _Shop()
    seller = User(
        email="asha@box.example.com",
        full_name="Asha Rao",
        password_hash="x",
        is_active=True,
    )
    shop.session.add(seller)
    shop.session.flush()
    shop.session.add(UserFirm(user_id=seller.id, firm_id=shop.firm_id, is_active=True))
    bill = _billed_by_the_box(shop)
    bill.salesman_id = seller.id
    bill.status = "APPROVED"
    shop.session.commit()
    commission = CommissionService(shop.session)
    commission.create_rule(
        CommissionRuleCreate(
            salesman_id=seller.id,
            percentage=D("0"),
            effective_from=date(2026, 4, 1),
            basis=CommissionBasisEnum.INVOICED,
            product_id=shop.setup.product.id,
            rate_type=CommissionRateTypeEnum.PER_UNIT,
            per_unit_amount=D("2.5"),
        ),
        firm_id=shop.firm_id,
        actor_id=shop.actor,
    )
    shop.session.commit()

    report = commission.report(
        firm_id=shop.firm_id, from_date=date(2026, 4, 1), to_date=date(2027, 3, 31)
    )

    [row] = [row for row in report.rows if row.salesman_id == seller.id]
    assert row.commission_amount == D("60.00")


# ---- pieces that are not whole boxes (D-PRC-37, D-PRC-38) -------------------
#
# The third live check (2026-10-06): a note of 2 BOX at 1,200.00, GST 18%,
# 2,832.00. Billed 7 PIECE with no price it was stored as 0.5833 BOX and
# worth 699.96, 825.95 with tax; with the other 17 at a typed 100.00 (stored
# at 1,199.9718 a box) the two bills came to 2,831.95.


def _shipped(shop: _Shop, quantity: str = "2", **line: object) -> DeliveryNoteLine:
    """Order, deliver and dispatch a line by the box; return the note's line."""
    order = shop.order(quantity=quantity, sales_uom_id=shop.box, **line)
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
                        "current_delivery_quantity": quantity,
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
    return shop.session.scalars(
        select(DeliveryNoteLine).where(DeliveryNoteLine.delivery_note_id == note.id)
    ).one()


def _bill(
    shop: _Shop, note_line: DeliveryNoteLine, quantity: str, **line: object
) -> tuple[SalesInvoice, SalesInvoiceLine]:
    """Bill some of a note line and approve the bill; return it and its line."""
    service = SalesInvoiceService(shop.session)
    bill = service.create_invoice(
        SalesInvoiceCreate.model_validate(
            {
                "customer_id": shop.setup.customer.id,
                "invoice_date": DAY,
                "lines": [
                    {
                        "source_document_type": "DELIVERY_NOTE",
                        "source_document_id": note_line.delivery_note_id,
                        "source_document_line_id": note_line.id,
                        "line_number": 1,
                        "current_invoice_quantity": quantity,
                    }
                    | line
                ],
            }
        ),
        firm_id=shop.firm_id,
        actor_id=shop.actor,
    )
    bill = service.approve_invoice(
        bill.id, firm_scope=shop.firm_id, actor_id=shop.actor
    )
    shop.session.expire_all()
    billed = shop.session.scalars(
        select(SalesInvoiceLine).where(SalesInvoiceLine.sales_invoice_id == bill.id)
    ).one()
    return bill, billed


def _gst_18(shop: _Shop) -> None:
    """Charge the shop's product GST at 18%."""
    shop.setup.product.tax_profile_group_code = "GST_STANDARD"
    shop.session.commit()
    _tax_group(
        shop.session,
        firm_id=shop.firm_id,
        percent="18",
        starts=date(2026, 4, 1),
        ends=None,
    )


def _on_hand(shop: _Shop) -> Decimal:
    """Return the pieces of the product the warehouse holds."""
    shop.session.expire_all()
    return D(
        str(
            shop.session.scalar(
                select(
                    func.coalesce(func.sum(InventoryRecord.current_quantity), 0)
                ).where(InventoryRecord.product_id == shop.setup.product.id)
            )
        )
    )


def test_seven_pieces_of_a_box_are_billed_as_seven_pieces() -> None:
    """7 PIECE are 700.00 and 826.00 with tax; with the other 17, 2,832.00."""
    shop = _Shop()
    _gst_18(shop)
    note_line = _shipped(shop)

    first, seven = _bill(shop, note_line, "7", invoice_uom_id=shop.piece)

    assert (seven.entered_quantity, seven.invoice_uom_id) == (D("7.0000"), shop.piece)
    # The cap still counts in the note line's unit, at the note's price.
    assert (seven.current_invoice_quantity, seven.unit_price) == (
        D("0.5833"),
        D("1200.0000"),
    )
    assert seven.conversion_factor == D("0.0833333333")
    assert (seven.gross_amount, seven.tax_amount) == (D("700.0000"), D("126.0000"))
    assert first.grand_total == D("826.0000")

    second, rest = _bill(
        shop, note_line, "17", invoice_uom_id=shop.piece, unit_price="100"
    )

    assert (rest.entered_quantity, rest.current_invoice_quantity) == (
        D("17.0000"),
        D("1.4167"),
    )
    # 100.00 a piece is 1,200.00 a box, not 1,199.9718.
    assert (rest.unit_price, rest.gross_amount) == (D("1200.0000"), D("1700.0000"))
    assert second.grand_total == D("2006.0000")
    assert first.grand_total + second.grand_total == D("2832.0000")
    assert (first.status, second.status) == ("APPROVED", "APPROVED")


def test_parts_in_pieces_that_round_up_as_boxes_still_bill_the_whole_note() -> None:
    """5, 5 and 14 PIECE are 2.0001 BOX rounded apart: the third is taken."""
    shop = _Shop()
    note_line = _shipped(shop)

    lines = [
        _bill(shop, note_line, quantity, invoice_uom_id=shop.piece)[1]
        for quantity in ("5", "5", "14")
    ]

    assert [line.current_invoice_quantity for line in lines] == [
        D("0.4167"),
        D("0.4167"),
        D("1.1666"),
    ]
    assert [line.gross_amount for line in lines] == [
        D("500.0000"),
        D("500.0000"),
        D("1400.0000"),
    ]
    with pytest.raises(ValidationError, match="exceeds the available source"):
        _bill(shop, note_line, "1", invoice_uom_id=shop.piece)
    shop.session.rollback()


def test_the_bill_that_completes_a_note_takes_what_the_others_left() -> None:
    """A box at 1,000.00 billed 4 + 4 + 4 pieces is 333.33 + 333.33 + 333.34."""
    shop = _Shop()
    note_line = _shipped(shop, "1", unit_price="1000")

    lines = [
        _bill(shop, note_line, "4", invoice_uom_id=shop.piece)[1] for _ in range(3)
    ]

    assert [line.gross_amount for line in lines] == [
        D("333.3333"),
        D("333.3333"),
        D("333.3400"),
    ]


def _brought_back(
    shop: _Shop, source: tuple[str, UUID, UUID], quantity: str, **line: object
) -> SalesReturnLine:
    """Raise, approve and complete a return of one line; return its line."""
    service = SalesReturnService(shop.session)
    row = service.create_return(
        SalesReturnCreate.model_validate(
            {
                "warehouse_id": shop.setup.warehouse.id,
                "return_date": DAY,
                "lines": [
                    {
                        "source_document_type": source[0],
                        "source_document_id": source[1],
                        "source_document_line_id": source[2],
                        "line_number": 1,
                        "current_return_quantity": quantity,
                    }
                    | line
                ],
            }
        ),
        firm_id=shop.firm_id,
        actor_id=shop.actor,
    )
    service.approve_return(row.id, firm_scope=shop.firm_id, actor_id=shop.actor)
    service.complete_return(row.id, firm_scope=shop.firm_id, actor_id=shop.actor)
    shop.session.expire_all()
    return shop.session.scalars(
        select(SalesReturnLine).where(SalesReturnLine.sales_return_id == row.id)
    ).one()


@pytest.mark.parametrize("billed_as", ["boxes", "pieces"])
def test_seven_pieces_come_back_off_a_bill_of_boxes(billed_as: str) -> None:
    """A return of 7 PIECE is credited 700.00 and puts 7 pieces on the shelf.

    Whether the bill it credits was typed 2 BOX or 24 PIECE: either way the
    bill line counts 2 of the note's boxes.
    """
    shop = _Shop()
    note_line = _shipped(shop)
    typed = (
        {"current": "24", "invoice_uom_id": shop.piece}
        if billed_as == "pieces"
        else {"current": "2"}
    )
    bill, billed = _bill(
        shop,
        note_line,
        str(typed.pop("current")),
        **typed,
    )
    assert billed.current_invoice_quantity == D("2.0000")
    held = _on_hand(shop)

    back = _brought_back(
        shop,
        ("SALES_INVOICE", bill.id, billed.id),
        "7",
        return_uom_id=shop.piece,
    )

    assert (back.entered_quantity, back.return_uom_id) == (D("7.0000"), shop.piece)
    assert (back.sales_uom_id, back.current_return_quantity) == (shop.box, D("0.5833"))
    assert (back.unit_price, back.gross_amount) == (D("1200.0000"), D("700.0000"))
    assert _on_hand(shop) == held + D("7")


def test_a_box_comes_back_off_a_note_as_twelve_pieces() -> None:
    """1 BOX off the note, and 12 PIECE off it, each put 12 pieces back."""
    shop = _Shop()
    note_line = _shipped(shop)
    held = _on_hand(shop)
    source = ("DELIVERY_NOTE", note_line.delivery_note_id, note_line.id)

    box = _brought_back(shop, source, "1")
    assert _on_hand(shop) == held + D("12")
    pieces = _brought_back(shop, source, "12", return_uom_id=shop.piece)

    assert (box.current_return_quantity, box.entered_quantity) == (D("1.0000"), None)
    assert (pieces.current_return_quantity, pieces.entered_quantity) == (
        D("1.0000"),
        D("12.0000"),
    )
    assert _on_hand(shop) == held + D("24")


def _owed(shop: _Shop, bill: SalesInvoice) -> Decimal:
    """Return what a bill still owes once its returns are taken off."""
    from app.settlements.services.settlement_service import credited_against

    shop.session.expire_all()
    credited = credited_against(
        shop.session, firm_id=shop.firm_id, invoice_ids=[bill.id]
    ).get(bill.id, D("0"))
    return D(str(shop.session.get(SalesInvoice, bill.id).grand_total)) - credited


def test_a_bill_returned_in_loose_pieces_is_credited_all_of_itself() -> None:
    """2 BOX at 1,200.00 back as 7, 7, 7 and 3 pieces: 2,832.00, not 2,831.93.

    Each part was capped at its share of the boxes still out as **stored**
    -- 0.5833 of 1.4167 where it is seven of seventeen pieces -- so the
    second and third came back at 699.98 and 699.95, and the bill read 0.07
    owed with every piece back (D-PRC-79). One of the four types the price
    of a piece, as the check that found it did.
    """
    shop = _Shop()
    _gst_18(shop)
    bill, billed = _bill(shop, _shipped(shop), "2")
    source = ("SALES_INVOICE", bill.id, billed.id)
    assert _owed(shop, bill) == D("2832.00")

    parts = [
        _brought_back(shop, source, "7", return_uom_id=shop.piece),
        _brought_back(shop, source, "7", return_uom_id=shop.piece, unit_price="100"),
        _brought_back(shop, source, "7", return_uom_id=shop.piece),
        _brought_back(shop, source, "3", return_uom_id=shop.piece),
    ]

    assert [part.net_amount - part.tax_amount for part in parts] == [
        D("700.0000"),
        D("700.0000"),
        D("700.0000"),
        D("300.0000"),
    ]
    assert [part.bill_discount_amount for part in parts] == [D("0.0000")] * 4
    assert _owed(shop, bill) == D("0.00")


def test_the_part_that_brings_back_the_last_of_a_line_takes_what_is_left() -> None:
    """A box at 100.00 back as three fours: 33.3333, 33.3333 and 33.3334.

    Three thirds rounded on their own are 99.9999; the last return takes
    what the bill line is still worth, so the parts add up to the line.
    """
    shop = _Shop()
    bill, billed = _bill(shop, _shipped(shop, "1", unit_price="100"), "1")
    source = ("SALES_INVOICE", bill.id, billed.id)

    parts = [
        _brought_back(shop, source, "4", return_uom_id=shop.piece) for _ in range(3)
    ]

    assert [part.net_amount for part in parts] == [
        D("33.3333"),
        D("33.3333"),
        D("33.3334"),
    ]
    assert sum(part.net_amount for part in parts) == billed.net_amount


def test_a_deduction_typed_on_the_last_part_of_a_line_stands() -> None:
    """The last four pieces typed at 8.00 where 8.33 was billed: 32.00."""
    shop = _Shop()
    bill, billed = _bill(shop, _shipped(shop, "1", unit_price="100"), "1")
    source = ("SALES_INVOICE", bill.id, billed.id)
    _brought_back(shop, source, "8", return_uom_id=shop.piece)

    last = _brought_back(shop, source, "4", return_uom_id=shop.piece, unit_price="8")

    assert last.net_amount == D("32.0000")


def test_half_a_box_typed_as_a_box_is_refused_where_it_is_saved() -> None:
    """0.5 BOX on a bill or a return never reaches approval or completion."""
    shop = _Shop()
    note_line = _shipped(shop)
    words = "BOX is counted in whole numbers, so 0.5 BOX cannot be entered."

    with pytest.raises(ValidationError) as on_the_bill:
        _bill(shop, note_line, "0.5")
    shop.session.rollback()
    with pytest.raises(ValidationError) as on_the_return:
        _brought_back(
            shop,
            ("DELIVERY_NOTE", note_line.delivery_note_id, note_line.id),
            "0.5",
            return_uom_id=shop.box,
        )
    shop.session.rollback()

    assert str(on_the_bill.value.message) == words
    assert str(on_the_return.value.message) == words
    assert shop.session.scalars(select(SalesInvoice)).all() == []
    assert shop.session.scalars(select(SalesReturn)).all() == []


# ---- the unit printed (D-PRC-40) -------------------------------------------
#
# The third live check: a note of 2 BOX billed as 24 PIECE printed "2 | PIECE
# | 1,200.00" on the tax invoice, and a box line billed in its own unit
# printed no unit at all while its order and challan printed BOX.


def test_a_per_unit_commission_stops_paying_for_pieces_that_came_back() -> None:
    """2 BOX billed, 7 PIECE back: 17 pieces at 2.50 are 42.50 (D-PRC-59).

    The return is stored as 0.5833 of a box, and 0.5833 of twelve is 6.9996
    pieces; the units are worked from the seven that were typed.
    """
    shop = _Shop()
    seller = User(
        email="asha@back.example.com",
        full_name="Asha Rao",
        password_hash="x",
        is_active=True,
    )
    shop.session.add(seller)
    shop.session.flush()
    shop.session.add(UserFirm(user_id=seller.id, firm_id=shop.firm_id, is_active=True))
    bill, billed = _bill(shop, _shipped(shop), "2")
    bill.salesman_id = seller.id
    shop.session.commit()
    commission = CommissionService(shop.session)
    commission.create_rule(
        CommissionRuleCreate(
            salesman_id=seller.id,
            percentage=D("0"),
            effective_from=date(2026, 4, 1),
            basis=CommissionBasisEnum.INVOICED,
            product_id=shop.setup.product.id,
            rate_type=CommissionRateTypeEnum.PER_UNIT,
            per_unit_amount=D("2.5"),
        ),
        firm_id=shop.firm_id,
        actor_id=shop.actor,
    )
    shop.session.commit()

    def earned() -> Decimal:
        """Return what the seller has earned over the year."""
        report = commission.report(
            firm_id=shop.firm_id, from_date=date(2026, 4, 1), to_date=date(2027, 3, 31)
        )
        [row] = [row for row in report.rows if row.salesman_id == seller.id]
        return row.commission_amount

    assert earned() == D("60.00")

    source = ("SALES_INVOICE", bill.id, billed.id)
    _brought_back(shop, source, "7", return_uom_id=shop.piece)
    assert earned() == D("42.50")

    _brought_back(shop, source, "17", return_uom_id=shop.piece)
    assert earned() == D("0.00")


def _printed(shop: _Shop, bill: SalesInvoice) -> tuple[Decimal, str | None, Decimal]:
    """Return the quantity, unit and rate the tax invoice prints for its line."""
    document = SalesInvoicePrintService(shop.session)._document(
        bill, firm_scope=shop.firm_id
    )
    [line] = document.lines
    return D(str(line.quantity)), line.uom, D(str(line.rate))


def test_a_bill_typed_in_pieces_prints_pieces_at_the_price_of_a_piece() -> None:
    """24 PIECE of 2 BOX prints 24 PIECE at 100.00; 7 prints 7 at 100.00."""
    shop = _Shop()
    whole, _ = _bill(shop, _shipped(shop), "24", invoice_uom_id=shop.piece)
    part, _ = _bill(shop, _shipped(shop), "7", invoice_uom_id=shop.piece)

    assert _printed(shop, whole) == (D("24.0000"), "PIECE", D("100.0000"))
    assert _printed(shop, part) == (D("7.0000"), "PIECE", D("100.0000"))


def test_a_box_line_billed_in_its_own_unit_prints_box() -> None:
    """2 with no unit named, of a note of 2 BOX, prints 2 BOX at 1,200.00."""
    shop = _Shop()
    bill, _ = _bill(shop, _shipped(shop), "2")

    assert _printed(shop, bill) == (D("2.0000"), "BOX", D("1200.0000"))


def test_a_bill_of_a_line_that_names_no_unit_prints_the_stock_unit() -> None:
    """A counter bill of 3 with no unit anywhere prints 3 PIECE."""
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
                        "current_invoice_quantity": "3",
                    }
                ],
            }
        ),
        firm_id=shop.firm_id,
        actor_id=shop.actor,
    )

    assert _printed(shop, bill) == (D("3.0000"), "PIECE", D("100.0000"))


def test_a_line_typed_before_it_kept_what_was_typed_prints_its_stored_unit() -> None:
    """An old row -- 2 stored, typed as PIECE, nothing kept -- prints 2 BOX."""
    shop = _Shop()
    bill, line = _bill(shop, _shipped(shop), "24", invoice_uom_id=shop.piece)
    line.entered_quantity = None
    shop.session.commit()

    assert _printed(shop, bill) == (D("2.0000"), "BOX", D("1200.0000"))


def test_a_credit_note_of_pieces_prints_pieces() -> None:
    """7 PIECE back off a bill of 2 BOX prints 7 PIECE at 100.00; 1 prints BOX."""
    shop = _Shop()
    bill, billed = _bill(shop, _shipped(shop), "2")
    source = ("SALES_INVOICE", bill.id, billed.id)

    def printed(line: SalesReturnLine) -> tuple[Decimal, str | None, Decimal]:
        """Return what the credit note prints for a return's one line."""
        row = shop.session.get(SalesReturn, line.sales_return_id)
        document = CreditNotePrintService(shop.session)._document(
            row, firm_scope=shop.firm_id
        )
        [stated] = document.lines
        return D(str(stated.quantity)), stated.uom, D(str(stated.rate))

    pieces = _brought_back(shop, source, "7", return_uom_id=shop.piece)
    box = _brought_back(shop, source, "1")

    assert printed(pieces) == (D("7.0000"), "PIECE", D("100.0000"))
    assert printed(box) == (D("1.0000"), "BOX", D("1200.0000"))


# ---- either unit field names the unit (D-PRC-44) ---------------------------
#
# The third live check: a counter bill line naming `order_uom_id` BOX and no
# `invoice_uom_id` was read as pieces -- 2 at 100.00, two pieces off the
# shelf, and the line came back with no unit.


def _counter_bill(shop: _Shop, **line: object) -> SalesInvoice:
    """Type a bill of 2 of the product straight in, with what the line names."""
    return SalesInvoiceService(shop.session).create_invoice(
        SalesInvoiceCreate.model_validate(
            {
                "customer_id": shop.setup.customer.id,
                "invoice_date": DAY,
                "lines": [
                    {
                        "product_id": shop.setup.product.id,
                        "line_number": 1,
                        "current_invoice_quantity": "2",
                    }
                    | line
                ],
            }
        ),
        firm_id=shop.firm_id,
        actor_id=shop.actor,
    )


@pytest.mark.parametrize("fields", ["order", "invoice", "both"])
def test_a_counter_bill_line_means_the_unit_either_field_names(fields: str) -> None:
    """2 naming BOX by `order_uom_id`, `invoice_uom_id` or both are 2 boxes."""
    shop = _Shop(counter=True)
    named = {
        "order": {"order_uom_id": shop.box},
        "invoice": {"invoice_uom_id": shop.box},
        "both": {"order_uom_id": shop.box, "invoice_uom_id": shop.box},
    }[fields]

    bill = _counter_bill(shop, **named)

    shop.session.expire_all()
    billed = shop.session.scalars(
        select(SalesInvoiceLine).where(SalesInvoiceLine.sales_invoice_id == bill.id)
    ).one()
    assert (billed.unit_price, billed.gross_amount) == (D("1200.0000"), D("2400.0000"))
    assert billed.order_uom_id == shop.box
    hidden = shop.session.scalars(select(SalesOrderLine)).one()
    assert (hidden.sales_uom_id, hidden.base_quantity) == (shop.box, D("24.0000"))
    assert shop.reserved() == D("24.0000")
    assert _printed(shop, bill) == (D("2.0000"), "BOX", D("1200.0000"))


def test_a_counter_bill_line_naming_two_units_is_refused_in_words() -> None:
    """BOX to order in and PIECE to bill in: neither is quietly dropped."""
    shop = _Shop(counter=True)

    with pytest.raises(ValidationError) as refused:
        _counter_bill(shop, order_uom_id=shop.box, invoice_uom_id=shop.piece)
    shop.session.rollback()

    assert str(refused.value.message) == (
        "Line 1 names two units: BOX as the unit it is ordered in and PIECE as "
        "the unit it is billed in. A line typed straight onto a bill is sold "
        "in one unit; name that unit once."
    )
    assert shop.session.scalars(select(SalesInvoice)).all() == []
    assert shop.session.scalars(select(SalesOrder)).all() == []


def _draft_of(shop: _Shop, note_line: DeliveryNoteLine, **line: object) -> SalesInvoice:
    """Save a draft bill of 24 of a note line, with what the line names."""
    return SalesInvoiceService(shop.session).create_invoice(
        SalesInvoiceCreate.model_validate(
            {
                "customer_id": shop.setup.customer.id,
                "invoice_date": DAY,
                "lines": [
                    {
                        "source_document_type": "DELIVERY_NOTE",
                        "source_document_id": note_line.delivery_note_id,
                        "source_document_line_id": note_line.id,
                        "line_number": 1,
                        "current_invoice_quantity": "24",
                    }
                    | line
                ],
            }
        ),
        firm_id=shop.firm_id,
        actor_id=shop.actor,
    )


@pytest.mark.parametrize("fields", ["order", "pair"])
def test_a_bill_of_a_note_means_the_unit_either_field_names(fields: str) -> None:
    """24 naming PIECE by `order_uom_id` alone bill the 2 BOX, as the pair does.

    Named by `order_uom_id` alone it was read as 24 boxes and refused as more
    than was shipped.
    """
    shop = _Shop()
    note_line = _shipped(shop)
    named = {
        "order": {"order_uom_id": shop.piece},
        "pair": {"order_uom_id": shop.box, "invoice_uom_id": shop.piece},
    }[fields]

    bill = _draft_of(shop, note_line, **named)

    shop.session.expire_all()
    billed = shop.session.scalars(
        select(SalesInvoiceLine).where(SalesInvoiceLine.sales_invoice_id == bill.id)
    ).one()
    assert (billed.current_invoice_quantity, billed.entered_quantity) == (
        D("2.0000"),
        D("24.0000"),
    )
    assert (billed.order_uom_id, billed.invoice_uom_id) == (shop.box, shop.piece)
    assert billed.gross_amount == D("2400.0000")


def test_an_ordered_unit_that_is_not_the_notes_is_refused_in_words() -> None:
    """Billed in PIECE and said to bill a line in PIECE, of a note in BOX."""
    shop = _Shop()
    note_line = _shipped(shop)

    with pytest.raises(ValidationError) as refused:
        _draft_of(shop, note_line, order_uom_id=shop.piece, invoice_uom_id=shop.piece)
    shop.session.rollback()

    message = str(refused.value.message)
    assert message.startswith("Line 1 says the line it bills is in PIECE, and DN-")
    assert message.endswith(
        " line 1 is in BOX. Leave the ordered unit off, or send BOX; the unit "
        "the line is billed in is the other field."
    )
    assert shop.session.scalars(select(SalesInvoice)).all() == []


# ---- the quantity declared (D-PRC-50) --------------------------------------
#
# The fourth live check: 7 PIECE back off a bill typed 24 PIECE left GSTR-1's
# HSN row reading 23.4167, and 24 PIECE, 2 BOX and 7 PIECE of one code read 33.


def _hsn(shop: _Shop) -> list[tuple[str, Decimal, Decimal]]:
    """Return the HSN summary's rows: unit, quantity and taxable value."""
    return [
        (row.unit, row.quantity, row.taxable_value)
        for row in GstSalesRegisterService(shop.session).hsn_summary(shop.firm_id)
    ]


def test_a_return_in_pieces_comes_off_the_hsn_summary_in_pieces() -> None:
    """24 PIECE billed and 7 PIECE back leave 17 PIECE worth 1,700.00."""
    shop = _Shop()
    bill, billed = _bill(shop, _shipped(shop), "24", invoice_uom_id=shop.piece)
    assert _hsn(shop) == [("PIECE", D("24.0000"), D("2400.00"))]

    _brought_back(
        shop, ("SALES_INVOICE", bill.id, billed.id), "7", return_uom_id=shop.piece
    )

    assert _hsn(shop) == [("PIECE", D("17.0000"), D("1700.00"))]


def test_the_hsn_summary_never_adds_pieces_to_boxes() -> None:
    """24 PIECE and 2 BOX of one code are two rows, and 4,800.00 between them."""
    shop = _Shop()
    _bill(shop, _shipped(shop), "24", invoice_uom_id=shop.piece)
    _bill(shop, _shipped(shop), "2")

    rows = _hsn(shop)

    assert rows == [
        ("BOX", D("2.0000"), D("2400.00")),
        ("PIECE", D("24.0000"), D("2400.00")),
    ]
    assert sum((taxable for _, _, taxable in rows), D("0")) == D("4800.00")


# ---- refusals that say what they count in (D-PRC-57) -----------------------


def test_a_return_refused_for_its_quantity_names_the_unit_it_counts_in() -> None:
    """Seven pieces back of 2 BOX, then 2 BOX more: "2 BOX sent, 0.5833 BOX".

    It read "(2.0000 sent, 0.5833 already returned)" to somebody who had
    typed pieces.
    """
    shop = _Shop()
    bill, billed = _bill(shop, _shipped(shop), "2")
    source = ("SALES_INVOICE", bill.id, billed.id)
    _brought_back(shop, source, "7", return_uom_id=shop.piece)

    with pytest.raises(ValidationError) as refused:
        _brought_back(shop, source, "2")
    shop.session.rollback()

    assert str(refused.value.message) == (
        "Return quantity exceeds what was dispatched on the source document "
        "(2 BOX sent, 0.5833 BOX already returned)."
    )


@pytest.mark.parametrize(
    ("stored", "said"),
    [
        ("0", "0"),
        ("0.0000", "0"),
        ("0E-14", "0"),
        ("1.00000000000000", "1"),
        ("0.5833", "0.5833"),
        ("1200.0000", "1200"),
        (None, "0"),
    ],
)
def test_a_quantity_in_a_message_is_spelt_one_way(
    stored: str | None, said: str
) -> None:
    """A nothing read 0, 0.0000 and 1.00000000000000 by the column it came off."""
    assert plain_quantity(None if stored is None else D(stored)) == said


def test_a_quantity_summed_across_a_factor_is_read_at_four_places() -> None:
    """One free unit times a ten-place factor read 1.00000000000000."""
    read = at_quantity_scale(D("1.00000000000000"))

    assert (read, read.as_tuple().exponent) == (D("1.0000"), -4)
    assert at_quantity_scale(None) == D("0.0000")
    assert at_quantity_scale("0.58335") == D("0.5834")


def test_a_note_in_boxes_over_the_cap_is_counted_in_boxes() -> None:
    """D-PRC-62: 3 BOX against 1 left read "36 PIECE where 12 PIECE" are left."""
    shop = _Shop()
    order = shop.order(quantity="4", sales_uom_id=shop.box)
    shop.orders.approve_order(order.id, firm_scope=shop.firm_id, actor_id=shop.actor)
    notes = DeliveryNoteService(shop.session)
    first = notes.get_note(
        _note_of(shop, order, "3", sales_uom_id=shop.box), firm_scope=shop.firm_id
    )
    second = notes.get_note(
        _note_of(shop, order, "3", sales_uom_id=shop.box), firm_scope=shop.firm_id
    )
    notes.approve_note(first.id, firm_scope=shop.firm_id, actor_id=shop.actor)

    with pytest.raises(ValidationError) as at_approval:
        notes.approve_note(second.id, firm_scope=shop.firm_id, actor_id=shop.actor)
    assert str(at_approval.value) == (
        f"Line 1 of {second.delivery_note_number} delivers 3 BOX where "
        f"{order.order_number} has 1 BOX left to deliver of the 4 BOX ordered: "
        f"{first.delivery_note_number} delivers the rest. Cancel this note and "
        "raise one for what is left, or cancel the other note first."
    )
    shop.session.rollback()
    # And where the note is saved, in the same words and the same unit.
    with pytest.raises(ValidationError) as at_save:
        _note_of(shop, order, "2", sales_uom_id=shop.box)
    assert str(at_save.value) == (
        f"Line 1 delivers 2 BOX where {order.order_number} has 1 BOX left to "
        f"deliver of the 4 BOX ordered: {first.delivery_note_number} delivers "
        "the rest. Change the line to what is left."
    )
