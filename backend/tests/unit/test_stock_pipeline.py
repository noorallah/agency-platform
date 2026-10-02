"""Incoming and outgoing beside available (STK-10, §70 row 14, decision A60).

*Incoming* is what approved purchase orders still bring; *outgoing* is what
open sales orders promise and have not yet set aside. Both are derived, never
stored, and the stock summary adds *projected* = available + incoming -
outgoing. The order editor's line shows the same figures for the warehouse it
ships from.
"""

# ruff: noqa: D103

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.goods_receipt.services import GoodsReceiptService
from app.inventory.services import InventoryService
from app.inventory.services.pipeline import incoming, outgoing
from app.purchase.models import PurchaseOrder
from app.sales.services.document_preview import line_companions
from app.sales_order.models import SalesOrderLine
from app.sales_order.schemas import SalesOrderCreate, SalesOrderLineWrite
from app.sales_order.services import SalesOrderService
from tests.unit.test_goods_receipt import _Fixture, _session_factory
from tests.unit.test_sales_order_module import _customer

# The receipt fixture types its order number; see conftest (D-CFG-2).
pytestmark = pytest.mark.typed_document_numbers


def _shop(code: str) -> _Fixture:
    """Build an approved order of 10 from the supplier, nothing received yet."""
    return _Fixture(_session_factory()(), code)


def _by_product(fixture: _Fixture) -> object:
    (row,) = [
        row
        for row in InventoryService(fixture.session).stock_by_product(
            firm_scope=fixture.firm.id
        )
        if row.scope_id == fixture.product.id
    ]
    return row


def _sell(fixture: _Fixture, quantity: str, *, reserved: str | None = None) -> UUID:
    """Approve a sales order for the product; optionally hold less reserved."""
    customer = _customer(fixture.session, firm_id=fixture.firm.id)
    service = SalesOrderService(fixture.session)
    order = service.create_order(
        SalesOrderCreate(
            customer_id=customer.id,
            branch_id=fixture.branch.id,
            warehouse_id=fixture.warehouse.id,
            order_date=fixture.order.purchase_date,
            lines=[
                SalesOrderLineWrite(
                    line_number=1,
                    product_id=fixture.product.id,
                    quantity=Decimal(quantity),
                    unit_price=Decimal("150"),
                )
            ],
        ),
        firm_id=fixture.firm.id,
        actor_id=uuid4(),
    )
    service.approve_order(order.id, firm_scope=fixture.firm.id, actor_id=uuid4())
    if reserved is not None:
        line = fixture.session.scalar(
            select(SalesOrderLine).where(SalesOrderLine.sales_order_id == order.id)
        )
        assert line is not None
        line.reserved_quantity = Decimal(reserved)
        fixture.session.commit()
    return customer.id


def test_an_approved_purchase_order_is_coming_in() -> None:
    fixture = _shop("PIP1")

    row = _by_product(fixture)

    assert row.incoming_quantity == Decimal("10")  # type: ignore[attr-defined]
    assert row.projected_quantity == Decimal("10")  # type: ignore[attr-defined]


def test_what_was_received_is_no_longer_coming() -> None:
    fixture = _shop("PIP2")
    receipts = GoodsReceiptService(fixture.session)
    receipt = receipts.create_receipt(
        fixture.receipt_payload("4"),
        firm_id=fixture.firm.id,
        actor_id=fixture.actor_id,
    )
    receipts.complete_receipt(
        receipt.id, firm_scope=fixture.firm.id, actor_id=fixture.actor_id
    )

    row = _by_product(fixture)

    assert row.available_quantity == Decimal("4")  # type: ignore[attr-defined]
    assert row.incoming_quantity == Decimal("6")  # type: ignore[attr-defined]
    assert row.projected_quantity == Decimal("10")  # type: ignore[attr-defined]


def test_a_draft_purchase_order_is_not_coming_in() -> None:
    fixture = _shop("PIP3")
    order = fixture.session.get(PurchaseOrder, fixture.order.id)
    assert order is not None
    order.status = "DRAFT"
    fixture.session.commit()

    assert incoming(fixture.session, firm_id=fixture.firm.id) == {}


def test_a_promise_not_yet_set_aside_is_going_out() -> None:
    fixture = _shop("PIP4")
    # Four promised, one reserved: three still to find.
    _sell(fixture, "4", reserved="1")

    key = (fixture.warehouse.id, fixture.product.id)
    assert outgoing(fixture.session, firm_id=fixture.firm.id)[key] == Decimal("3")
    row = _by_product(fixture)
    assert row.outgoing_quantity == Decimal("3")  # type: ignore[attr-defined]
    # Available already lost the reserved one: 0 - 1 + 10 incoming - 3.
    assert row.projected_quantity == (  # type: ignore[attr-defined]
        row.available_quantity + Decimal("10") - Decimal("3")  # type: ignore[attr-defined]
    )


def test_a_fully_reserved_order_is_not_counted_twice() -> None:
    fixture = _shop("PIP5")
    _sell(fixture, "4")

    assert outgoing(fixture.session, firm_id=fixture.firm.id) == {}


def test_the_warehouse_summary_carries_them_too() -> None:
    fixture = _shop("PIP6")
    _sell(fixture, "4", reserved="0")

    (row,) = [
        row
        for row in InventoryService(fixture.session).stock_by_warehouse(
            firm_scope=fixture.firm.id
        )
        if row.scope_id == fixture.warehouse.id
    ]

    assert row.incoming_quantity == Decimal("10")
    assert row.outgoing_quantity == Decimal("4")


def test_the_order_line_shows_them_for_its_warehouse() -> None:
    fixture = _shop("PIP7")
    customer_id = _sell(fixture, "4", reserved="0")

    (line,) = line_companions(
        fixture.session,
        firm_id=fixture.firm.id,
        customer_id=customer_id,
        lines=[(1, fixture.product.id, fixture.warehouse.id)],
    )

    assert (line.incoming_quantity, line.outgoing_quantity) == (
        Decimal("10"),
        Decimal("4"),
    )
