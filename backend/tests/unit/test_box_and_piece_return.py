"""A sales return of lines typed as boxes and pieces (L5 step 5).

`docs/design/BOX_AND_PIECE_LINE_DESIGN.md`, 3.4, 3.6 and 3.8. A return line
comes back at the pack of the note or bill line it returns, so a box of 12
sold before the item moved to 10 is returned as a box of 12, and the return
starts in the layout of what it returns. The caps stay sums of pieces. The
``pack_size`` a screen sends is a precondition, never the figure stored.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select

from app.core.exceptions import ValidationError
from app.sales_invoice.models import SalesInvoice, SalesInvoiceLine
from app.sales_invoice.services import SalesInvoiceService
from app.sales_return.models import SalesReturn, SalesReturnLine
from app.sales_return.schemas import SalesReturnCreate
from app.sales_return.services import SalesReturnService
from tests.unit.test_box_and_piece_note_and_bill import (
    LATER,
    _bill_line,
    _counter_bill,
    _shipped,
)
from tests.unit.test_box_and_piece_sales import _gst_12, _ten_to_a_box_from
from tests.unit.test_lines_in_another_unit import _Shop
from tests.unit.test_selling_unit_default import _sold_by_the_box

D = Decimal


def _billed(shop: _Shop) -> tuple[SalesInvoice, SalesInvoiceLine]:
    """Bill and approve the worked example straight in: 41 + 2 free at 12."""
    service = SalesInvoiceService(shop.session)
    bill = service.create_invoice(
        _counter_bill(shop), firm_id=shop.firm_id, actor_id=shop.actor
    )
    bill = service.approve_invoice(
        bill.id, firm_scope=shop.firm_id, actor_id=shop.actor
    )
    return bill, _bill_line(shop, bill.id)


def _return_body(
    shop: _Shop, source: tuple[str, UUID, UUID], quantity: str, **line: object
) -> SalesReturnCreate:
    """Return a return of one source line, with what the line names."""
    return SalesReturnCreate.model_validate(
        {
            "warehouse_id": shop.setup.warehouse.id,
            "return_date": LATER,
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
    )


def _return_line(shop: _Shop, return_id: UUID) -> SalesReturnLine:
    """Return the return's one line, as stored."""
    shop.session.expire_all()
    return shop.session.scalars(
        select(SalesReturnLine).where(SalesReturnLine.sales_return_id == return_id)
    ).one()


def test_the_worked_example_comes_back_to_the_paisa() -> None:
    """1 box + 1 piece back off the bill: 13 pieces, 130.00 + 15.60 GST."""
    shop = _sold_by_the_box(counter=True)
    _gst_12(shop)
    bill, billed = _billed(shop)
    service = SalesReturnService(shop.session)

    row = service.create_return(
        _return_body(shop, ("SALES_INVOICE", bill.id, billed.id), "13", pack_size="12"),
        firm_id=shop.firm_id,
        actor_id=shop.actor,
    )

    line = _return_line(shop, row.id)
    assert line.current_return_quantity == D("13.0000")
    assert (line.pack_uom_id, line.pack_size) == (shop.box, D("12.0000"))
    assert (line.gross_amount, line.tax_amount) == (D("130.0000"), D("15.6000"))
    answered = service.return_response(row)
    assert answered.box_and_piece_entry is True
    assert (answered.lines[0].pack_uom_id, answered.lines[0].pack_size) == (
        shop.box,
        D("12.0000"),
    )


def test_a_return_after_the_box_changes_comes_back_at_the_bills_pack() -> None:
    """Billed at 12 to a box, returned at 12 once the box holds 10."""
    shop = _sold_by_the_box(counter=True)
    bill, billed = _billed(shop)
    _ten_to_a_box_from(shop, date(2026, 8, 5))
    service = SalesReturnService(shop.session)
    source = ("SALES_INVOICE", bill.id, billed.id)

    with pytest.raises(ValidationError, match="holds 12, not 10"):
        service.create_return(
            _return_body(shop, source, "13", pack_size="10"),
            firm_id=shop.firm_id,
            actor_id=shop.actor,
        )
    row = service.create_return(
        _return_body(shop, source, "13", pack_size="12"),
        firm_id=shop.firm_id,
        actor_id=shop.actor,
    )

    assert _return_line(shop, row.id).pack_size == D("12.0000")


def test_a_return_off_a_note_takes_the_notes_pack_and_layout() -> None:
    """The note shipped at 12 to a box; more pieces than it sent cannot come back."""
    shop = _sold_by_the_box()
    note, note_line = _shipped(shop)
    service = SalesReturnService(shop.session)
    source = ("DELIVERY_NOTE", note.id, note_line.id)

    row = service.create_return(
        _return_body(shop, source, "13", pack_size="12"),
        firm_id=shop.firm_id,
        actor_id=shop.actor,
    )

    assert row.box_and_piece_entry is True
    line = _return_line(shop, row.id)
    assert (line.pack_uom_id, line.pack_size) == (shop.box, D("12.0000"))
    # The cap is a sum of pieces: 30 against what the note sent.
    with pytest.raises(ValidationError, match="exceeds"):
        service.update_return(
            row.id,
            _return_body(shop, source, "30", pack_size="12"),
            firm_scope=shop.firm_id,
            actor_id=shop.actor,
        )


def test_an_update_saying_nothing_of_the_layout_keeps_it() -> None:
    """Absent on an update keeps the return's own; false says so outright."""
    shop = _sold_by_the_box(counter=True)
    bill, billed = _billed(shop)
    service = SalesReturnService(shop.session)
    body = _return_body(shop, ("SALES_INVOICE", bill.id, billed.id), "13")
    row = service.create_return(body, firm_id=shop.firm_id, actor_id=shop.actor)

    service.update_return(
        row.id,
        body.model_copy(update={"box_and_piece_entry": False}),
        firm_scope=shop.firm_id,
        actor_id=shop.actor,
    )
    service.update_return(row.id, body, firm_scope=shop.firm_id, actor_id=shop.actor)

    assert shop.session.get(SalesReturn, row.id).box_and_piece_entry is False  # type: ignore[union-attr]


def test_boxes_and_pieces_naming_another_unit_are_refused() -> None:
    """A line typed as boxes and pieces is counted in pieces, not in boxes."""
    shop = _sold_by_the_box(counter=True)
    bill, billed = _billed(shop)

    with pytest.raises(ValidationError, match="stock unit"):
        SalesReturnService(shop.session).create_return(
            _return_body(
                shop,
                ("SALES_INVOICE", bill.id, billed.id),
                "1",
                pack_size="12",
                return_uom_id=shop.box,
            ),
            firm_id=shop.firm_id,
            actor_id=shop.actor,
        )
