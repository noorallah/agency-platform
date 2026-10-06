"""A note's inherited free goods are settled when the note is approved.

D-PRC-29: an order of 10 with 3 free, delivered by notes of 3 and 7 that were
both saved as drafts before either was approved, shipped 0 + 2 free. Each
draft worked its share against the notes already approved, and with neither
approved the second did not know it completed the line. One unit never left,
and the order stayed part-delivered with it reserved.

The share a silent line takes is worked again at approval, from the notes
approved before it. Whatever order the drafts were typed or approved in, the
notes of a line ship exactly the order's free units, whole, and the one that
completes the line takes what is left. A typed figure is not touched. Every
case runs on a request-shaped session.
"""

from decimal import Decimal

import pytest

from app.core.exceptions import ValidationError
from app.core.utils.pricing import continued_share
from app.delivery_note.models import DeliveryNote, DeliveryNoteLineBatch
from app.sales_order.models import SalesOrder
from tests.unit.test_order_bill_discount_reaches_the_bill import _Trade

D = Decimal


class _TwoDrafts(_Trade):
    """An order of 10 with 3 free, and drafts of 3 and 7 saved side by side."""

    def __init__(self, **second: object) -> None:
        """Save both drafts before approving either."""
        super().__init__()
        self.sale: SalesOrder = self.order("10", free_quantity="3")
        self.first: DeliveryNote = self.note(self.sale, "3", ship=False)
        self.second: DeliveryNote = self.note(self.sale, "7", ship=False, **second)

    def ship(self, note: DeliveryNote) -> DeliveryNote:
        """Approve and dispatch one of the drafts."""
        self.notes.approve_note(note.id, firm_scope=self.firm_id, actor_id=self.actor)
        self.notes.dispatch_note(note.id, firm_scope=self.firm_id, actor_id=self.actor)
        self.session.expire_all()
        return self.notes.get_note(note.id, firm_scope=self.firm_id)

    def free(self, note: DeliveryNote) -> Decimal:
        """Return the free units a note's line ships."""
        self.session.expire_all()
        return self.note_line(note).free_quantity


def test_as_drafts_the_two_notes_state_fewer_free_goods_than_the_order() -> None:
    """The reproduction's starting point: 0 and 2, of 3."""
    trade = _TwoDrafts()

    assert (trade.free(trade.first), trade.free(trade.second)) == (D("0"), D("2.0000"))
    assert trade.note_line(trade.first).free_quantity_inherited is True


def test_approved_in_the_order_typed_they_ship_the_orders_free_goods() -> None:
    """3 then 7: the note that completes the line takes all three."""
    trade = _TwoDrafts()

    first = trade.ship(trade.first)
    second = trade.ship(trade.second)

    assert (trade.free(first), trade.free(second)) == (D("0.0000"), D("3.0000"))
    # Seven charged and three free leave the shelf on the second note.
    assert trade.note_line(second).delivered_quantity == D("10.0000")
    assert second.total_free_quantity == D("3.0000")
    assert second.total_current_delivery_quantity == D("10.0000")
    trade.session.expire_all()
    order = trade.orders.get_order(trade.sale.id, firm_scope=trade.firm_id)
    assert order.status == "DELIVERED"
    assert trade.order_line(order).reserved_quantity == D("0.0000")


def test_approved_the_other_way_round_they_still_ship_three() -> None:
    """7 then 3: 2 go with the seven and the last one with the three."""
    trade = _TwoDrafts()

    second = trade.ship(trade.second)
    first = trade.ship(trade.first)

    assert (trade.free(second), trade.free(first)) == (D("2.0000"), D("1.0000"))
    trade.session.expire_all()
    order = trade.orders.get_order(trade.sale.id, firm_scope=trade.firm_id)
    assert order.status == "DELIVERED"


def test_three_drafts_ship_whole_units_that_sum_to_the_order() -> None:
    """4, 3 and 3 of ten with 3 free: 1, 1 and the last one."""
    trade = _Trade()
    order = trade.order("10", free_quantity="3")
    drafts = [trade.note(order, part, ship=False) for part in ("4", "3", "3")]

    given = []
    for draft in drafts:
        trade.notes.approve_note(
            draft.id, firm_scope=trade.firm_id, actor_id=trade.actor
        )
        trade.notes.dispatch_note(
            draft.id, firm_scope=trade.firm_id, actor_id=trade.actor
        )
        trade.session.expire_all()
        given.append(trade.note_line(draft).free_quantity)

    assert given == [D("1.0000"), D("1.0000"), D("1.0000")]
    assert all(units == units.to_integral_value() for units in given)


def test_a_typed_figure_is_not_worked_again() -> None:
    """A zero typed on the completing note still ships none."""
    trade = _TwoDrafts(free_quantity="0")
    assert trade.note_line(trade.second).free_quantity_inherited is False

    trade.ship(trade.first)
    second = trade.ship(trade.second)

    assert trade.free(second) == D("0.0000")


def test_a_note_approved_alone_keeps_the_figure_it_was_saved_with() -> None:
    """Nothing else was approved in between: approval moves nothing."""
    trade = _Trade()
    order = trade.order("10", free_quantity="3")
    draft = trade.note(order, "4", ship=False)
    assert trade.note_line(draft).free_quantity == D("1.0000")

    trade.notes.approve_note(draft.id, firm_scope=trade.firm_id, actor_id=trade.actor)
    trade.session.expire_all()

    line = trade.note_line(draft)
    assert (line.free_quantity, line.delivered_quantity) == (D("1.0000"), D("5.0000"))


def test_a_line_with_batches_picked_is_asked_to_be_saved_again() -> None:
    """Its picks were made for the old figure, so the person re-saves it."""
    trade = _TwoDrafts()
    trade.ship(trade.first)
    line = trade.note_line(trade.second)
    trade.session.add(
        DeliveryNoteLineBatch(
            delivery_note_line_id=line.id,
            firm_id=trade.firm_id,
            batch_id=line.id,
            quantity=D("9"),
        )
    )
    trade.session.commit()

    with pytest.raises(ValidationError) as refused:
        trade.notes.approve_note(
            trade.second.id, firm_scope=trade.firm_id, actor_id=trade.actor
        )
    trade.session.rollback()

    assert str(refused.value.message) == (
        f"Line 1 of {trade.second.delivery_note_number} now ships 3 free, not "
        "2: another delivery of the same order line was approved since this "
        "note was saved. Save the note again so the batches or serial numbers "
        "picked cover what it ships."
    )


def test_the_money_of_two_drafts_can_miss_the_orders_by_a_ten_thousandth() -> None:
    """Known and not closed here: two drafts each slice from nothing shipped.

    12.3455 off a line of ten, sliced as 3 and 7 with nothing before either,
    is 3.7037 + 8.6419 = 12.3456. Approved in turn the second would take
    what the first left (8.6418). The residual is at most 0.0001 a line, below
    the paisa the ledger posts in; closing it means taxing the line again at
    approval.
    """
    whole, amount = D("10"), D("12.3455")
    apart = continued_share(
        amount, before=D("0"), part=D("3"), whole=whole
    ) + continued_share(amount, before=D("0"), part=D("7"), whole=whole)
    in_turn = continued_share(
        amount, before=D("0"), part=D("3"), whole=whole
    ) + continued_share(amount, before=D("3"), part=D("7"), whole=whole)

    assert (apart, in_turn) == (D("12.3456"), D("12.3455"))
