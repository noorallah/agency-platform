"""A typed receipt brings in no more free goods than its order has left.

D-BUY-67: a bill off an order was held to the order line's free goods
(D-PRC-90) and a receipt that typed its own free figure was not, so an order
of 10 with 2 free, received in two parts with 2 typed free on each, put 4
free units on the shelf.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.exceptions import ValidationError
from app.goods_receipt.models import GoodsReceipt
from app.goods_receipt.schemas import GoodsReceiptCreate, GoodsReceiptUpdate
from app.goods_receipt.services import GoodsReceiptService
from tests.unit.test_goods_receipt import _Fixture, _session_factory

# The shared fixture types its order's number; see conftest (D-CFG-2).
pytestmark = pytest.mark.typed_document_numbers


def _shop(code: str, free: str = "2") -> _Fixture:
    """Return a firm whose approved order of 10 carries free goods."""
    fixture = _Fixture(_session_factory()(), code)
    fixture.order_line.free_quantity = Decimal(free)
    fixture.session.commit()
    return fixture


def _payload(fixture: _Fixture, quantity: str, free: str) -> GoodsReceiptCreate:
    """Return a receipt of the order's line with a typed free figure."""
    data = fixture.receipt_payload(quantity).model_dump()
    data["lines"][0]["free_quantity"] = Decimal(free)
    return GoodsReceiptCreate.model_validate(data)


def _receive(fixture: _Fixture, quantity: str, free: str) -> GoodsReceipt:
    """Save a draft receipt of the order's line."""
    return GoodsReceiptService(fixture.session).create_receipt(
        _payload(fixture, quantity, free),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )


def test_two_parts_share_the_order_lines_free_goods() -> None:
    """The second part is refused what the first already took."""
    fixture = _shop("FRE1")
    first = _receive(fixture, "5", "2")
    assert first.total_free_quantity == Decimal("2")

    with pytest.raises(ValidationError) as refused:
        _receive(fixture, "5", "1")
    message = str(refused.value)
    assert "Line 1 brings in 1 free" in message
    assert f"line 1 of {fixture.order.po_number} has 0 left to give" in message
    assert "2 free on the order, 2 already received" in message

    second = _receive(fixture, "5", "0")
    assert second.total_free_quantity == Decimal("0")


def test_a_draft_receipt_counts_and_a_cancelled_one_gives_back() -> None:
    """A draft holds its share; cancelling it frees the share again."""
    fixture = _shop("FRE2")
    service = GoodsReceiptService(fixture.session)
    first = _receive(fixture, "5", "1")
    with pytest.raises(ValidationError, match="has 1 left to give"):
        _receive(fixture, "5", "2")

    service.cancel_receipt(
        first.id,
        firm_scope=fixture.firm.id,
        actor_id=fixture.actor_id,
        reason="Typed against the wrong order",
    )
    again = _receive(fixture, "5", "2")
    assert again.total_free_quantity == Decimal("2")


def test_an_order_that_promised_none_takes_none() -> None:
    """A line whose order offers no free goods can type none."""
    fixture = _shop("FRE3", free="0")
    with pytest.raises(ValidationError, match="0 free on the order"):
        _receive(fixture, "4", "1")
    assert _receive(fixture, "4", "0").total_free_quantity == Decimal("0")


def test_an_edit_is_not_counted_against_its_own_earlier_figure() -> None:
    """Saving a receipt again measures it against the others only."""
    fixture = _shop("FRE4")
    service = GoodsReceiptService(fixture.session)
    receipt = _receive(fixture, "5", "2")

    def edit(free: str) -> GoodsReceipt:
        """Save the receipt again with another free figure."""
        return service.update_receipt(
            receipt.id,
            GoodsReceiptUpdate.model_validate(
                _payload(fixture, "5", free).model_dump()
            ),
            firm_scope=fixture.firm.id,
            actor_id=fixture.actor_id,
        )

    assert edit("1").total_free_quantity == Decimal("1")
    assert edit("2").total_free_quantity == Decimal("2")
    with pytest.raises(ValidationError, match="has 2 left to give"):
        edit("3")


def test_two_lines_of_one_order_line_share_what_it_has() -> None:
    """Two receipt lines of one order line are added together."""
    fixture = _shop("FRE5")
    data = fixture.receipt_payload("3").model_dump()
    data["lines"][0]["free_quantity"] = Decimal("1")
    data["lines"].append(data["lines"][0] | {"line_number": 2})
    receipt = GoodsReceiptService(fixture.session).create_receipt(
        GoodsReceiptCreate.model_validate(data),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    assert receipt.total_free_quantity == Decimal("2")

    other = _shop("FRE6")
    data = other.receipt_payload("3").model_dump()
    data["lines"][0]["free_quantity"] = Decimal("2")
    data["lines"].append(data["lines"][0] | {"line_number": 2})
    with pytest.raises(ValidationError, match="Line 2 brings in 2 free"):
        GoodsReceiptService(other.session).create_receipt(
            GoodsReceiptCreate.model_validate(data),
            firm_id=other.firm.id,
            actor_id=other.actor_id,
        )
