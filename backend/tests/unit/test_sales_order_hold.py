"""Stopping a sales order without unwinding it.

The design turns on one decision: **a hold is a flag, not a status.** An order
that is PARTIALLY_DELIVERED can be held, and releasing it has to put it back to
PARTIALLY_DELIVERED rather than guess -- writing HOLD into `status` would
destroy the only record of how far the order had got.

The rest follows:

- a hold has to **stop something**, or it is a switch somebody flicks believing
  the goods have stopped moving while they carry on out of the warehouse;
- the stock stays **reserved**, because holding says "not yet", not "never";
- and the reason is **kept after release**, because "why was this held" is the
  question asked afterwards.
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.branches.models import Branch, Warehouse
from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.customers.models import Customer
from app.delivery_note.schemas import DeliveryNoteCreate, DeliveryNoteLineWrite
from app.delivery_note.services import DeliveryNoteService
from app.firms.models import Firm
from app.products.models import Product
from app.sales_order.models import SalesOrder, SalesOrderLine
from app.sales_order.services import SalesOrderService

WHEN = date(2026, 6, 10)


def _session_factory() -> sessionmaker[Session]:
    """Create one shared in-memory database."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


class _Books:
    """A firm with one approved order that could be dispatched."""

    def __init__(self, session: Session) -> None:
        """Seed the firm, its masters and an approved order."""
        self.session = session
        self.actor_id = uuid4()
        self.firm = Firm(
            name="Hold Firm",
            code="HOLD",
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
        )
        session.add(self.firm)
        session.commit()
        self.branch = Branch(
            firm_id=self.firm.id,
            code="BR-1",
            name="Branch One",
            display_name="Branch One",
            currency_code="INR",
            working_hours={"start": "09:00", "end": "18:00"},
            status="ACTIVE",
        )
        session.add(self.branch)
        session.flush()
        self.warehouse = Warehouse(
            firm_id=self.firm.id,
            branch_id=self.branch.id,
            code="WH-1",
            name="Warehouse One",
            display_name="Warehouse One",
            status="ACTIVE",
        )
        self.customer = Customer(
            firm_id=self.firm.id,
            code="C1",
            customer_type="BUSINESS",
            name="Kumar Stores",
            display_name="Kumar Stores",
            currency_code="INR",
            status="ACTIVE",
        )
        self.product = Product(
            firm_id=self.firm.id,
            code="SKU-1",
            name="Toothpaste 150g",
            product_type="STOCK_ITEM",
            status="ACTIVE",
        )
        session.add_all([self.warehouse, self.customer, self.product])
        session.commit()
        self.order, self.line = self._order()

    def _order(self, status: str = "APPROVED") -> tuple[SalesOrder, SalesOrderLine]:
        """Raise an order with one line."""
        order = SalesOrder(
            firm_id=self.firm.id,
            customer_id=self.customer.id,
            branch_id=self.branch.id,
            warehouse_id=self.warehouse.id,
            order_number=f"SO-{uuid4().hex[:6].upper()}",
            order_date=WHEN,
            status=status,
            currency_code="INR",
        )
        self.session.add(order)
        self.session.flush()
        line = SalesOrderLine(
            sales_order_id=order.id,
            firm_id=self.firm.id,
            line_number=1,
            product_id=self.product.id,
            quantity=Decimal("10"),
            base_quantity=Decimal("10"),
            reservable_quantity=Decimal("10"),
            reserved_quantity=Decimal("10"),
            unit_price=Decimal("100"),
            gross_amount=Decimal("1000"),
            net_amount=Decimal("1000"),
            warehouse_id=self.warehouse.id,
        )
        self.session.add(line)
        self.session.commit()
        return order, line

    def hold(
        self, reason: str = "Awaiting the customer's purchase order."
    ) -> SalesOrder:
        """Put the seeded order on hold."""
        return SalesOrderService(self.session).hold_order(
            self.order.id,
            reason=reason,
            firm_scope=self.firm.id,
            actor_id=self.actor_id,
        )

    def release(self) -> SalesOrder:
        """Lift the hold."""
        return SalesOrderService(self.session).release_order(
            self.order.id, firm_scope=self.firm.id, actor_id=self.actor_id
        )

    def dispatch(self) -> object:
        """Try to raise a delivery note against the order."""
        return DeliveryNoteService(self.session).create_note(
            DeliveryNoteCreate(
                sales_order_id=self.order.id,
                delivery_date=WHEN,
                lines=[
                    DeliveryNoteLineWrite(
                        sales_order_line_id=self.line.id,
                        line_number=1,
                        current_delivery_quantity=Decimal("1"),
                    )
                ],
            ),
            firm_id=self.firm.id,
            actor_id=self.actor_id,
        )


def test_holding_leaves_the_status_exactly_where_it_was() -> None:
    """A hold is a flag, not a status.

    Writing HOLD into `status` would destroy the only record of how far the
    order had got, and the release would then have to guess.
    """
    books = _Books(_session_factory()())
    books.order.status = "PARTIALLY_DELIVERED"
    books.session.commit()

    row = books.hold()

    assert row.is_on_hold is True
    assert row.status == "PARTIALLY_DELIVERED"


def test_releasing_puts_it_back_where_it_was() -> None:
    """Nothing was overwritten, so nothing has to be restored."""
    books = _Books(_session_factory()())
    books.order.status = "PARTIALLY_DELIVERED"
    books.session.commit()
    books.hold()

    row = books.release()

    assert row.is_on_hold is False
    assert row.status == "PARTIALLY_DELIVERED"


def test_a_held_order_cannot_be_dispatched() -> None:
    """The point of a hold.

    A flag the engine records that changed no outcome would be a switch
    somebody turns on believing the goods have stopped moving, while they
    carry on out of the warehouse.
    """
    books = _Books(_session_factory()())
    books.hold(reason="Payment not cleared.")

    with pytest.raises(ValidationError, match="on hold"):
        books.dispatch()


def test_the_refusal_says_why_it_is_held() -> None:
    """The person hitting the wall is the one who has to get it lifted."""
    books = _Books(_session_factory()())
    books.hold(reason="Awaiting the signed contract.")

    with pytest.raises(ValidationError, match="Awaiting the signed contract"):
        books.dispatch()


def test_the_stock_stays_reserved_while_it_is_held() -> None:
    """Holding says "not yet", not "never".

    Releasing the goods would let another order take them while this one
    waits, and the customer is still promised them.
    """
    books = _Books(_session_factory()())

    books.hold()

    books.session.refresh(books.line)
    assert books.line.reserved_quantity == Decimal("10.0000")


def test_the_reason_survives_the_release() -> None:
    """Why the order was held is the question asked afterwards."""
    books = _Books(_session_factory()())
    books.hold(reason="Customer asked us to wait for their warehouse move.")

    row = books.release()

    assert row.hold_reason == "Customer asked us to wait for their warehouse move."
    assert row.released_at is not None


def test_a_released_order_can_be_dispatched_again() -> None:
    """A hold that could not be lifted would be a cancellation."""
    books = _Books(_session_factory()())
    books.hold()
    books.release()

    assert books.dispatch() is not None


def test_an_order_cannot_be_held_twice() -> None:
    """The second would overwrite the first reason with no record of it."""
    books = _Books(_session_factory()())
    books.hold(reason="First reason.")

    with pytest.raises(ValidationError, match="already on hold"):
        books.hold(reason="Second reason.")


def test_an_order_that_is_not_held_cannot_be_released() -> None:
    """Silently succeeding would let a screen report a hold it never lifted."""
    books = _Books(_session_factory()())

    with pytest.raises(ValidationError, match="not on hold"):
        books.release()


def test_a_cancelled_order_has_nothing_left_to_hold() -> None:
    """Nor a closed one. Both are finished."""
    books = _Books(_session_factory()())
    books.order.status = "CANCELLED"
    books.session.commit()

    with pytest.raises(ValidationError, match="nothing left to hold"):
        books.hold()


def test_holding_clears_any_earlier_release_stamp() -> None:
    """Or the record reads as released while the order is held."""
    books = _Books(_session_factory()())
    books.hold()
    books.release()

    row = books.hold(reason="Held again.")

    assert row.released_at is None
    assert row.held_at is not None
