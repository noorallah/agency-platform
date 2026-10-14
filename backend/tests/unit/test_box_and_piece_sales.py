"""A quotation or order line typed as boxes and pieces (L5 step 3).

`docs/design/BOX_AND_PIECE_LINE_DESIGN.md`, 3.3 to 3.6. A line typed as boxes
and pieces is a line in the stock unit: its quantity is the total in pieces
and its rate the rate of a piece. Beside it the line keeps the pack it was
written at -- the item's on the document's date, a saved draft line's own, or
the quoted line's on an order the quotation became. The ``pack_size`` the
screen sends is a precondition, never the figure stored.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.exceptions import ValidationError
from app.quotation.models import SalesQuotationLine
from app.quotation.schemas import QuotationCreate
from app.quotation.services.quotation_service import QuotationService
from app.sales_order.models import SalesOrder
from app.uom.models import ConversionRule
from tests.unit.test_lines_in_another_unit import DAY, _Shop
from tests.unit.test_sales_order_module import _tax_group
from tests.unit.test_selling_unit_default import _order_body, _quote, _sold_by_the_box

D = Decimal

#: The worked example of the design note's section 1: 3 boxes + 5 pieces of
#: a box of 12 at 10.00 a piece, and 0 boxes + 2 pieces free.
SALE = {"quantity": "41", "free_quantity": "2", "unit_price": "10", "pack_size": "12"}


def _gst_12(shop: _Shop) -> None:
    """Charge the shop's product GST at 12%, as the worked example does."""
    shop.setup.product.tax_profile_group_code = "GST_STANDARD"
    shop.session.commit()
    _tax_group(
        shop.session,
        firm_id=shop.firm_id,
        percent="12",
        starts=date(2026, 4, 1),
        ends=None,
    )


def _ten_to_a_box_from(shop: _Shop, starts: date) -> None:
    """Move the box from 12 to 10, as a new version of the rule."""
    shop.session.add(
        ConversionRule(
            firm_id=shop.firm_id,
            product_id=shop.setup.product.id,
            from_uom_id=shop.box,
            to_uom_id=shop.piece,
            conversion_factor=D("10"),
            rounding_mode="HALF_UP",
            precision_scale=4,
            effective_from=starts,
            version_number=2,
        )
    )
    shop.session.commit()


def _update(shop: _Shop, order: SalesOrder, **line: object) -> None:
    """Send the order's draft back with its one line as given."""
    shop.orders.update_order(
        order.id,
        _order_body(shop, **line),
        firm_scope=shop.firm_id,
        actor_id=shop.actor,
    )


def test_the_worked_example_is_sold_to_the_paisa() -> None:
    """41 at 10.00 a piece and 2 free: 410.00 + 49.20 GST, 43 pieces to go."""
    shop = _sold_by_the_box()
    _gst_12(shop)

    order = shop.order(**SALE)

    line = shop.line(order)
    assert (line.sales_uom_id, line.inventory_uom_id) == (None, shop.piece)
    assert (line.quantity, line.free_quantity) == (D("41.0000"), D("2.0000"))
    assert (line.conversion_factor, line.base_quantity) == (D("1"), D("43.0000"))
    assert (line.gross_amount, line.tax_amount) == (D("410.0000"), D("49.2000"))
    assert line.net_amount == D("459.2000")
    assert (line.pack_uom_id, line.pack_size) == (shop.box, D("12.0000"))


def test_the_order_answers_its_pack_and_its_layout() -> None:
    """The response carries the line's pack and the header's layout flag."""
    shop = _sold_by_the_box()
    order = shop.orders.create_order(
        _order_body(shop, **SALE).model_copy(update={"box_and_piece_entry": True}),
        firm_id=shop.firm_id,
        actor_id=shop.actor,
    )

    response = shop.orders.order_response(order)

    assert response.box_and_piece_entry is True
    assert (response.lines[0].pack_uom_id, response.lines[0].pack_size) == (
        shop.box,
        D("12.0000"),
    )


def test_an_update_saying_nothing_of_the_layout_keeps_it() -> None:
    """Absent leaves the flag alone; a value sent is the value."""
    shop = _sold_by_the_box()
    order = shop.orders.create_order(
        _order_body(shop, **SALE).model_copy(update={"box_and_piece_entry": True}),
        firm_id=shop.firm_id,
        actor_id=shop.actor,
    )

    _update(shop, order, **SALE)
    assert shop.session.get(SalesOrder, order.id).box_and_piece_entry is True  # type: ignore[union-attr]

    shop.orders.update_order(
        order.id,
        _order_body(shop, **SALE).model_copy(update={"box_and_piece_entry": False}),
        firm_scope=shop.firm_id,
        actor_id=shop.actor,
    )
    assert shop.session.get(SalesOrder, order.id).box_and_piece_entry is False  # type: ignore[union-attr]


def test_a_pack_size_the_item_does_not_have_is_refused() -> None:
    """Rule 2: cells added up at a stale size would make a wrong total."""
    shop = _sold_by_the_box()

    with pytest.raises(
        ValidationError, match="Line 1: a box of this item holds 12, not 10"
    ):
        shop.order(**(SALE | {"pack_size": "10"}))


def test_boxes_and_pieces_of_an_item_with_no_pack_are_refused() -> None:
    """An item sold in its stock unit has no box to count in."""
    shop = _Shop()

    with pytest.raises(ValidationError, match="has no box"):
        shop.order(**SALE)
    line = shop.line(shop.order(quantity="41"))
    assert (line.pack_uom_id, line.pack_size) == (None, None)


def test_boxes_and_pieces_naming_another_unit_are_refused() -> None:
    """A line typed as boxes and pieces is counted in pieces, not in boxes."""
    shop = _sold_by_the_box()

    with pytest.raises(ValidationError, match="stock unit"):
        shop.order(**(SALE | {"sales_uom_id": shop.box}))


def test_a_line_in_boxes_still_records_the_pack() -> None:
    """Rule of 3.8: the pack is kept on any line of an item that has one."""
    shop = _sold_by_the_box()

    line = shop.line(shop.order())

    assert (line.sales_uom_id, line.base_quantity) == (shop.box, D("24.0000"))
    assert (line.pack_uom_id, line.pack_size) == (shop.box, D("12.0000"))


def test_a_draft_keeps_its_pack_after_the_box_changes() -> None:
    """3.3: a saved line reads 12 to a box for ever; a new order reads 10."""
    shop = _sold_by_the_box()
    order = shop.order(**SALE)
    _ten_to_a_box_from(shop, date(2026, 8, 1))

    _update(shop, order, **(SALE | {"quantity": "29"}))

    line = shop.line(order)
    assert (line.quantity, line.pack_size) == (D("29.0000"), D("12.0000"))
    with pytest.raises(ValidationError, match="holds 12, not 10"):
        _update(shop, order, **(SALE | {"pack_size": "10"}))
    shop.session.rollback()
    fresh = shop.line(shop.order(**(SALE | {"pack_size": "10"})))
    assert fresh.pack_size == D("10.0000")


def _quoted(shop: _Shop) -> SalesQuotationLine:
    """Return the shop's one quotation line, as stored."""
    shop.session.expire_all()
    return shop.session.scalars(select(SalesQuotationLine)).one()


def _quote_body(shop: _Shop) -> QuotationCreate:
    """Return a quotation of the worked example's sale, typed in boxes."""
    return QuotationCreate.model_validate(
        {
            "customer_id": shop.setup.customer.id,
            "branch_id": shop.setup.branch.id,
            "warehouse_id": shop.setup.warehouse.id,
            "quotation_date": DAY,
            "valid_until": date(2027, 12, 31),
            "box_and_piece_entry": True,
            "lines": [{"line_number": 1, "product_id": shop.setup.product.id} | SALE],
        }
    )


def test_a_quotation_line_keeps_the_pack_and_the_order_inherits_it() -> None:
    """3.6: a quote at 12 to a box is ordered at 12 after the box became 10."""
    shop = _sold_by_the_box()
    service = QuotationService(shop.session)
    quote = service.create_quotation(
        _quote_body(shop),
        firm_id=shop.firm_id,
        actor_id=shop.actor,
    )
    quoted = _quoted(shop)
    assert (quoted.pack_uom_id, quoted.pack_size) == (shop.box, D("12.0000"))
    assert quoted.gross_amount == D("410.0000")
    answered = service.quotation_response(quote)
    assert answered.box_and_piece_entry is True
    assert answered.lines[0].pack_size == D("12.0000")
    _ten_to_a_box_from(shop, date(2026, 8, 1))
    service.send_quotation(quote.id, firm_scope=shop.firm_id, actor_id=shop.actor)
    service.accept_quotation(quote.id, firm_scope=shop.firm_id, actor_id=shop.actor)

    _, order = service.convert_quotation(
        quote.id, firm_scope=shop.firm_id, actor_id=shop.actor, order_date=DAY
    )

    line = shop.line(order)
    assert (line.quantity, line.base_quantity) == (D("41.0000"), D("43.0000"))
    assert (line.pack_uom_id, line.pack_size) == (shop.box, D("12.0000"))
    assert line.gross_amount == D("410.0000")
    assert order.box_and_piece_entry is True


def test_a_stale_pack_size_on_a_quotation_is_refused() -> None:
    """The quotation asks the same precondition as the order."""
    shop = _sold_by_the_box()

    with pytest.raises(ValidationError, match="holds 12, not 6"):
        _quote(shop, **(SALE | {"pack_size": "6"}))
