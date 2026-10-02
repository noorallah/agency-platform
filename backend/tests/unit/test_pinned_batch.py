"""Pinning the batch a customer asked for on a sales order line (79 row 4).

The shop from ``test_batch_picker``: STALE (expired), MARCH and JUNE, ten
each, and an order for eight already holding MARCH. A second order pins JUNE.
"""

from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select

from app.core.exceptions import ValidationError
from app.delivery_note.models import DeliveryNoteLine, DeliveryNoteLineBatch
from app.delivery_note.schemas import DeliveryNoteCreate, DeliveryNoteLineWrite
from app.sales_order.models import SalesOrder, SalesOrderLine
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services import SalesOrderService
from tests.unit.test_batch_picker import NOTE_DATE, _Shop


def _pinned_order(shop: _Shop, batch: str, quantity: str = "5") -> SalesOrder:
    """Raise a draft order for ``quantity``, pinning one batch by name."""
    return SalesOrderService(shop.session).create_order(
        SalesOrderCreate(
            customer_id=shop.order.customer_id,
            branch_id=shop.order.branch_id,
            warehouse_id=shop.warehouse_id,
            order_date=NOTE_DATE,
            lines=[
                SalesOrderLineWrite(
                    line_number=1,
                    product_id=shop.product.id,
                    quantity=Decimal(quantity),
                    unit_price=Decimal("100"),
                    pinned_batch_id=shop.batches[batch].id,
                )
            ],
        ),
        firm_id=shop.firm_id,
        actor_id=shop.actor_id,
    )


def _approve(shop: _Shop, order: SalesOrder) -> SalesOrder:
    """Approve an order, which reserves."""
    return SalesOrderService(shop.session).approve_order(
        order.id, firm_scope=shop.firm_id, actor_id=shop.actor_id
    )


def _line(shop: _Shop, order: SalesOrder) -> SalesOrderLine:
    """Return the order's only line."""
    row = shop.session.scalar(
        select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order.id)
    )
    assert row is not None
    return row


def test_approval_holds_the_pinned_batch_not_the_earliest() -> None:
    """JUNE is held although MARCH expires first and has stock free."""
    shop = _Shop()
    march_before = shop.stock("MARCH").reserved_quantity

    _approve(shop, _pinned_order(shop, "JUNE"))

    assert shop.stock("JUNE").reserved_quantity == Decimal("5.0000")
    assert shop.stock("MARCH").reserved_quantity == march_before


def test_a_note_from_the_order_starts_with_the_pinned_batch_and_ships_it() -> None:
    """The note's line is pre-picked with JUNE, and dispatch draws JUNE."""
    shop = _Shop()
    order = _approve(shop, _pinned_order(shop, "JUNE"))
    note = shop.notes.create_note(
        DeliveryNoteCreate(
            sales_order_id=order.id,
            delivery_date=NOTE_DATE,
            lines=[
                DeliveryNoteLineWrite(
                    sales_order_line_id=_line(shop, order).id,
                    line_number=1,
                    current_delivery_quantity=Decimal("5"),
                    unit_price=Decimal("100"),
                )
            ],
        ),
        firm_id=shop.firm_id,
        actor_id=shop.actor_id,
    )
    note_line = shop.session.scalar(
        select(DeliveryNoteLine).where(DeliveryNoteLine.delivery_note_id == note.id)
    )
    assert note_line is not None
    picks = shop.session.scalars(
        select(DeliveryNoteLineBatch).where(
            DeliveryNoteLineBatch.delivery_note_line_id == note_line.id
        )
    ).all()
    assert [(row.batch_id, row.quantity) for row in picks] == [
        (shop.batches["JUNE"].id, Decimal("5.0000"))
    ]

    shop.dispatch(note)

    assert shop.drawn(note) == {"JUNE": Decimal("5.0000")}


def test_more_than_the_pinned_batch_holds_is_a_back_order() -> None:
    """Twelve of JUNE's ten: ten held from JUNE, nothing from MARCH."""
    shop = _Shop()
    march_before = shop.stock("MARCH").reserved_quantity

    _approve(shop, _pinned_order(shop, "JUNE", quantity="12"))

    assert shop.stock("JUNE").reserved_quantity == Decimal("10.0000")
    assert shop.stock("MARCH").reserved_quantity == march_before


def test_an_expired_pinned_batch_is_refused_at_approval() -> None:
    """Named, rather than held as a back order nobody can explain."""
    shop = _Shop()
    order = _pinned_order(shop, "STALE")

    with pytest.raises(ValidationError, match="STALE, has expired"):
        _approve(shop, order)


def test_another_products_batch_cannot_be_pinned() -> None:
    """Refused when the line is written."""
    shop = _Shop()
    other = shop.batches["JUNE"]
    other.product_id = UUID(int=1)
    shop.session.commit()

    with pytest.raises(ValidationError, match="Line 1: that batch is not"):
        _pinned_order(shop, "JUNE")
