"""A hold with no stock behind it stops nobody (D-STK-39).

An order holds its whole quantity, short stock or not, and the part nothing
covers sat on the stock row as a hold like any other. The dispatch gate read
the plain sum, so four on the shelf could not leave for an order of ten, nor
for an order of three once a later order had asked for four.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.branches.models import Branch, Warehouse
from app.core.exceptions import ValidationError
from app.customers.models import Customer
from app.firms.models import Firm
from app.inventory.models import InventoryRecord
from app.inventory.services import InventoryService
from app.products.models import Product
from tests.unit.test_delivery_note_module import (
    _approved_order,
    _branch,
    _customer,
    _dispatch,
    _firm,
    _product,
    _session_factory,
    _stock,
    _warehouse,
)

_World = tuple[Session, Firm, Branch, Warehouse, Customer, Product, UUID]


def _world(held: str) -> _World:
    """Build a firm holding ``held`` of one untracked product."""
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    customer = _customer(session, firm_id=firm.id)
    product = _product(session, firm_id=firm.id)
    _stock(
        session,
        firm=firm,
        branch=branch,
        warehouse=warehouse,
        product=product,
        quantity=Decimal(held),
    )
    return session, firm, branch, warehouse, customer, product, uuid4()


def _row(session: Session, product: Product) -> InventoryRecord:
    """Return the product's one stock row, read afresh."""
    row = session.scalar(
        select(InventoryRecord).where(InventoryRecord.product_id == product.id)
    )
    assert row is not None
    session.refresh(row)
    return row


def test_an_order_for_more_than_is_held_ships_what_is_held() -> None:
    """Ten ordered, four held: the four leave and six stay owed."""
    session, firm, branch, warehouse, customer, product, actor = _world("4")
    order, line = _approved_order(
        session,
        firm=firm,
        branch=branch,
        warehouse=warehouse,
        customer=customer,
        product=product,
        quantity=Decimal("10"),
        actor_id=actor,
    )

    _dispatch(
        session,
        firm=firm,
        order=order,
        order_line=line,
        quantity=Decimal("4"),
        on=date(2026, 8, 4),
        actor_id=actor,
    )

    row = _row(session, product)
    assert row.current_quantity == Decimal("0")
    assert row.reserved_quantity == Decimal("6"), "the six owed stay held"


def test_a_later_order_does_not_stop_an_earlier_one() -> None:
    """Four held, three ordered and then four: the three ship, the four wait."""
    session, firm, branch, warehouse, customer, product, actor = _world("4")
    places = {
        "firm": firm,
        "branch": branch,
        "warehouse": warehouse,
        "customer": customer,
        "product": product,
    }
    first, first_line = _approved_order(
        session, quantity=Decimal("3"), actor_id=actor, **places
    )
    second, second_line = _approved_order(
        session, quantity=Decimal("4"), actor_id=actor, **places
    )

    # The later order asks first, and is told to wait: three of the four
    # stand behind the earlier order's hold.
    with pytest.raises(ValidationError, match="Insufficient available stock"):
        _dispatch(
            session,
            firm=firm,
            order=second,
            order_line=second_line,
            quantity=Decimal("4"),
            on=date(2026, 8, 4),
            actor_id=actor,
        )
    session.rollback()

    _dispatch(
        session,
        firm=firm,
        order=first,
        order_line=first_line,
        quantity=Decimal("3"),
        on=date(2026, 8, 4),
        actor_id=actor,
    )

    row = _row(session, product)
    assert row.current_quantity == Decimal("1")
    assert row.reserved_quantity == Decimal("4"), "the later order's hold stands"


def test_stock_that_arrives_goes_to_the_earlier_order_first() -> None:
    """A later order's hold does not take goods the earlier one is owed."""
    session, firm, branch, warehouse, customer, product, actor = _world("4")
    places = {
        "firm": firm,
        "branch": branch,
        "warehouse": warehouse,
        "customer": customer,
        "product": product,
    }
    early, early_line = _approved_order(
        session, quantity=Decimal("10"), actor_id=actor, **places
    )
    late, late_line = _approved_order(
        session, quantity=Decimal("2"), actor_id=actor, **places
    )
    _stock(
        session,
        firm=firm,
        branch=branch,
        warehouse=warehouse,
        product=product,
        quantity=Decimal("3"),
    )

    shippable, _ = InventoryService(session).shippable_past_back_orders(
        firm_scope=firm.id,
        branch_id=branch.id,
        warehouse_id=warehouse.id,
        storage_node_id=None,
        product_id=product.id,
        reference_number=late.order_number,
    )
    assert shippable == Decimal("0"), "all seven stand behind the earlier order"

    _dispatch(
        session,
        firm=firm,
        order=early,
        order_line=early_line,
        quantity=Decimal("7"),
        on=date(2026, 8, 4),
        actor_id=actor,
    )
    assert _row(session, product).current_quantity == Decimal("0")
    assert late_line.reserved_quantity == Decimal("2")


def test_a_row_that_covers_its_holds_is_read_as_before() -> None:
    """Nothing is looked past where the stock covers every hold."""
    session, firm, branch, warehouse, customer, product, actor = _world("10")
    order, _ = _approved_order(
        session,
        firm=firm,
        branch=branch,
        warehouse=warehouse,
        customer=customer,
        product=product,
        quantity=Decimal("6"),
        actor_id=actor,
    )

    answer = InventoryService(session).shippable_past_back_orders(
        firm_scope=firm.id,
        branch_id=branch.id,
        warehouse_id=warehouse.id,
        storage_node_id=None,
        product_id=product.id,
        reference_number=order.order_number,
    )

    assert answer == (Decimal("0"), {})
