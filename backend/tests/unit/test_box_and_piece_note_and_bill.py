"""A delivery note and a sales bill of lines typed as boxes and pieces (L5 step 4).

`docs/design/BOX_AND_PIECE_LINE_DESIGN.md`, 3.3, 3.6 and 3.8. A note line
ships at its order line's pack and a bill line is billed at its note line's,
so 3 boxes + 5 ordered at 12 to a box are delivered and billed so after the
item moved to 10. A bill typed straight in hands its layout and each line's
``pack_size`` to the order and the note raised behind it. The ``pack_size``
a screen sends is a precondition, never the figure stored.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select

from app.core.exceptions import ValidationError
from app.delivery_note.models import DeliveryNote, DeliveryNoteLine
from app.delivery_note.schemas import DeliveryNoteCreate
from app.delivery_note.services.delivery_note_service import DeliveryNoteService
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine
from app.sales_invoice.schemas import SalesInvoiceCreate
from app.sales_invoice.services import SalesInvoiceService
from app.sales_order.models import SalesOrder, SalesOrderLine
from tests.unit.test_box_and_piece_sales import SALE, _ten_to_a_box_from
from tests.unit.test_lines_in_another_unit import DAY, _Shop
from tests.unit.test_selling_unit_default import _order_body, _sold_by_the_box

D = Decimal

#: A day after the order, once the box holds 10.
LATER = date(2026, 8, 6)


def _ordered(shop: _Shop, *, boxes: bool = True) -> SalesOrder:
    """Save and approve the worked example's order, typed in boxes and pieces."""
    order = shop.orders.create_order(
        _order_body(shop, **SALE).model_copy(update={"box_and_piece_entry": boxes}),
        firm_id=shop.firm_id,
        actor_id=shop.actor,
    )
    shop.orders.approve_order(order.id, firm_scope=shop.firm_id, actor_id=shop.actor)
    return order


def _note_body(
    shop: _Shop, order: SalesOrder, quantity: str = "24", **line: object
) -> DeliveryNoteCreate:
    """Return a note of the order's one line, with what the line names."""
    return DeliveryNoteCreate.model_validate(
        {
            "sales_order_id": order.id,
            "delivery_date": LATER,
            "lines": [
                {
                    "sales_order_line_id": shop.line(order).id,
                    "line_number": 1,
                    "current_delivery_quantity": quantity,
                }
                | line
            ],
        }
    )


def _note_line(shop: _Shop, note_id: UUID) -> DeliveryNoteLine:
    """Return the note's one line, as stored."""
    shop.session.expire_all()
    return shop.session.scalars(
        select(DeliveryNoteLine).where(DeliveryNoteLine.delivery_note_id == note_id)
    ).one()


def _bill_line(shop: _Shop, bill_id: UUID) -> SalesInvoiceLine:
    """Return the bill's one line, as stored."""
    shop.session.expire_all()
    return shop.session.scalars(
        select(SalesInvoiceLine).where(SalesInvoiceLine.sales_invoice_id == bill_id)
    ).one()


def test_a_part_delivery_ships_at_the_orders_pack_after_the_box_changes() -> None:
    """24 of 41 ordered at 12 to a box ship at 12 once the box holds 10."""
    shop = _sold_by_the_box()
    order = _ordered(shop)
    _ten_to_a_box_from(shop, date(2026, 8, 5))
    notes = DeliveryNoteService(shop.session)

    note = notes.create_note(
        _note_body(shop, order, pack_size="12"),
        firm_id=shop.firm_id,
        actor_id=shop.actor,
    )

    line = _note_line(shop, note.id)
    assert line.current_delivery_quantity == D("24.0000")
    assert (line.pack_uom_id, line.pack_size) == (shop.box, D("12.0000"))
    answered = notes.note_response(note)
    assert answered.box_and_piece_entry is True
    assert answered.lines[0].pack_size == D("12.0000")


def test_a_note_typed_at_a_stale_pack_size_is_refused() -> None:
    """Rule 2: the note's cells are added up at its order line's pack."""
    shop = _sold_by_the_box()
    order = _ordered(shop)
    _ten_to_a_box_from(shop, date(2026, 8, 5))

    with pytest.raises(ValidationError, match="holds 12, not 10"):
        DeliveryNoteService(shop.session).create_note(
            _note_body(shop, order, pack_size="10"),
            firm_id=shop.firm_id,
            actor_id=shop.actor,
        )


def test_a_note_takes_its_orders_layout_and_an_update_keeps_its_own() -> None:
    """3.8: raised from the order it starts so; absent on an update keeps it."""
    shop = _sold_by_the_box()
    plain = _ordered(shop, boxes=False)
    notes = DeliveryNoteService(shop.session)
    note = notes.create_note(
        _note_body(shop, plain), firm_id=shop.firm_id, actor_id=shop.actor
    )
    assert note.box_and_piece_entry is False

    notes.update_note(
        note.id,
        _note_body(shop, plain).model_copy(update={"box_and_piece_entry": True}),
        firm_scope=shop.firm_id,
        actor_id=shop.actor,
    )
    notes.update_note(
        note.id, _note_body(shop, plain), firm_scope=shop.firm_id, actor_id=shop.actor
    )

    assert shop.session.get(DeliveryNote, note.id).box_and_piece_entry is True  # type: ignore[union-attr]


def _shipped(shop: _Shop) -> tuple[DeliveryNote, DeliveryNoteLine]:
    """Ship 24 of the worked example's order, after the box moved to 10."""
    order = _ordered(shop)
    _ten_to_a_box_from(shop, date(2026, 8, 5))
    notes = DeliveryNoteService(shop.session)
    note = notes.create_note(
        _note_body(shop, order), firm_id=shop.firm_id, actor_id=shop.actor
    )
    notes.approve_note(note.id, firm_scope=shop.firm_id, actor_id=shop.actor)
    notes.dispatch_note(note.id, firm_scope=shop.firm_id, actor_id=shop.actor)
    return note, _note_line(shop, note.id)


def _bill_of(
    shop: _Shop, note: DeliveryNote, note_line: DeliveryNoteLine, **line: object
) -> SalesInvoiceCreate:
    """Return a bill of the whole note line, with what the line names."""
    return SalesInvoiceCreate.model_validate(
        {
            "customer_id": shop.setup.customer.id,
            "invoice_date": LATER,
            "lines": [
                {
                    "source_document_type": "DELIVERY_NOTE",
                    "source_document_id": note.id,
                    "source_document_line_id": note_line.id,
                    "line_number": 1,
                    "current_invoice_quantity": "24",
                }
                | line
            ],
        }
    )


def test_a_bill_of_a_note_is_billed_at_the_notes_pack() -> None:
    """The note shipped at 12, so the bill reads 2 x 12 + 0 at 240.00."""
    shop = _sold_by_the_box()
    note, note_line = _shipped(shop)
    service = SalesInvoiceService(shop.session)

    bill = service.create_invoice(
        _bill_of(shop, note, note_line, pack_size="12"),
        firm_id=shop.firm_id,
        actor_id=shop.actor,
    )

    line = _bill_line(shop, bill.id)
    assert (line.pack_uom_id, line.pack_size) == (shop.box, D("12.0000"))
    assert line.gross_amount == D("240.0000")
    answered = service.invoice_response(bill)
    assert answered.box_and_piece_entry is True
    assert (answered.lines[0].pack_uom_id, answered.lines[0].pack_size) == (
        shop.box,
        D("12.0000"),
    )


def test_a_bill_typed_at_a_stale_pack_size_is_refused() -> None:
    """The bill asks the same precondition of the note line it bills."""
    shop = _sold_by_the_box()
    note, note_line = _shipped(shop)

    with pytest.raises(ValidationError, match="holds 12, not 10"):
        SalesInvoiceService(shop.session).create_invoice(
            _bill_of(shop, note, note_line, pack_size="10"),
            firm_id=shop.firm_id,
            actor_id=shop.actor,
        )


def _counter_bill(shop: _Shop, **line: object) -> SalesInvoiceCreate:
    """Return a bill typed straight in: the worked example, in boxes."""
    return SalesInvoiceCreate.model_validate(
        {
            "customer_id": shop.setup.customer.id,
            "invoice_date": DAY,
            "box_and_piece_entry": True,
            "lines": [
                {
                    "product_id": shop.setup.product.id,
                    "line_number": 1,
                    "current_invoice_quantity": "41",
                    "free_quantity": "2",
                    "unit_price": "10",
                    "invoice_uom_id": shop.piece,
                    "pack_size": "12",
                }
                | line
            ],
        }
    )


def test_a_bill_typed_straight_in_hands_its_pack_and_layout_down() -> None:
    """The order and the note raised behind it hold 12 and the boxes layout."""
    shop = _sold_by_the_box(counter=True)

    bill = SalesInvoiceService(shop.session).create_invoice(
        _counter_bill(shop), firm_id=shop.firm_id, actor_id=shop.actor
    )

    order_line = shop.session.scalars(select(SalesOrderLine)).one()
    note_line = shop.session.scalars(select(DeliveryNoteLine)).one()
    line = _bill_line(shop, bill.id)
    for held in (order_line, note_line, line):
        assert (held.pack_uom_id, held.pack_size) == (shop.box, D("12.0000"))
    assert line.gross_amount == D("410.0000")
    assert shop.session.scalars(select(SalesOrder.box_and_piece_entry)).one() is True
    assert shop.session.scalars(select(DeliveryNote.box_and_piece_entry)).one() is True
    assert bill.box_and_piece_entry is True


def test_a_bill_typed_straight_in_at_a_stale_pack_size_is_refused() -> None:
    """Checked on the order it raises, before anything is kept."""
    shop = _sold_by_the_box(counter=True)

    with pytest.raises(ValidationError, match="holds 12, not 10"):
        SalesInvoiceService(shop.session).create_invoice(
            _counter_bill(shop, pack_size="10"),
            firm_id=shop.firm_id,
            actor_id=shop.actor,
        )


def test_a_counter_bill_edited_after_the_box_changes_keeps_its_pack() -> None:
    """Its order and note are raised again today, yet the line stays at 12."""
    shop = _sold_by_the_box(counter=True)
    service = SalesInvoiceService(shop.session)
    bill = service.create_invoice(
        _counter_bill(shop), firm_id=shop.firm_id, actor_id=shop.actor
    )
    _ten_to_a_box_from(shop, date(2026, 8, 1))

    service.update_invoice(
        bill.id,
        _counter_bill(shop, current_invoice_quantity="29").model_copy(
            update={"box_and_piece_entry": None}
        ),
        firm_id=shop.firm_id,
        actor_id=shop.actor,
    )

    line = _bill_line(shop, bill.id)
    assert (line.current_invoice_quantity, line.pack_size) == (
        D("29.0000"),
        D("12.0000"),
    )
    live = shop.session.scalars(
        select(SalesOrder).where(SalesOrder.status != "CANCELLED")
    ).all()
    assert [order.box_and_piece_entry for order in live] == [True]
    assert shop.session.get(SalesInvoice, bill.id).box_and_piece_entry is True  # type: ignore[union-attr]


def test_the_preview_answers_each_lines_pack() -> None:
    """The preview prices the bill as saving it would, pack included."""
    shop = _sold_by_the_box(counter=True)

    preview = SalesInvoiceService(shop.session).preview_invoice(
        _counter_bill(shop), firm_id=shop.firm_id, actor_id=shop.actor
    )

    assert preview.invoice.box_and_piece_entry is True
    assert preview.invoice.lines[0].pack_size == D("12.0000")
