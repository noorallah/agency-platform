"""A note line naming no bin ships what stands in the warehouse's bins (D-STK-54).

The dispatch gate read one storage place. Four in a bin and a note for four
that named no bin was refused for want of stock, and the refusal did not say
the goods were there.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.branches.models import Branch, Warehouse, WarehouseStorageNode
from app.core.exceptions import ValidationError
from app.customers.models import Customer
from app.firms.models import Firm
from app.inventory.models import InventoryRecord, InventoryTransaction
from app.inventory.schemas import InventoryAdjustmentCreate
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


def _world() -> _World:
    """Build a firm with one untracked product and nothing on the shelf."""
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    warehouse = _warehouse(session, firm_id=firm.id, branch_id=branch.id)
    customer = _customer(session, firm_id=firm.id)
    product = _product(session, firm_id=firm.id)
    return session, firm, branch, warehouse, customer, product, uuid4()


def _bin(session: Session, warehouse: Warehouse, code: str) -> UUID:
    """Add a bin to the warehouse and return its id."""
    node = WarehouseStorageNode(
        warehouse_id=warehouse.id,
        node_type="BIN",
        code=code,
        name=f"Bin {code}",
        path=code,
    )
    session.add(node)
    session.commit()
    return node.id


def _into_bin(
    session: Session,
    *,
    firm: Firm,
    branch: Branch,
    warehouse: Warehouse,
    product: Product,
    node_id: UUID,
    quantity: str,
) -> None:
    """Put a quantity of the product into one bin."""
    InventoryService(session).create_adjustment(
        InventoryAdjustmentCreate(
            branch_id=branch.id,
            warehouse_id=warehouse.id,
            storage_node_id=node_id,
            product_id=product.id,
            quantity=Decimal(quantity),
            reference_number=f"ADJ-BIN-{quantity}",
            reference_type="ADJUSTMENT",
            transaction_date=date(2026, 8, 3),
        ),
        firm_scope=firm.id,
        actor_id=uuid4(),
    )


def _held(session: Session, product: Product) -> dict[UUID | None, Decimal]:
    """Return what the product holds on hand, by storage place."""
    session.expire_all()
    return {
        row.storage_node_id: Decimal(str(row.current_quantity))
        for row in session.scalars(
            select(InventoryRecord).where(InventoryRecord.product_id == product.id)
        )
    }


def test_a_line_naming_no_bin_ships_what_a_bin_holds() -> None:
    """Four in a bin, ten ordered: the four leave the bin and six stay owed."""
    session, firm, branch, warehouse, customer, product, actor = _world()
    node_id = _bin(session, warehouse, "B1")
    places = {"firm": firm, "branch": branch, "warehouse": warehouse}
    _into_bin(session, product=product, node_id=node_id, quantity="4", **places)
    order, line = _approved_order(
        session,
        customer=customer,
        product=product,
        quantity=Decimal("10"),
        actor_id=actor,
        **places,
    )

    note = _dispatch(
        session,
        firm=firm,
        order=order,
        order_line=line,
        quantity=Decimal("4"),
        on=date(2026, 8, 4),
        actor_id=actor,
    )

    assert _held(session, product)[node_id] == Decimal("0")
    assert line.reserved_quantity == Decimal("6"), "the six owed stay held"
    left_from = session.scalars(
        select(InventoryTransaction.storage_node_id).where(
            InventoryTransaction.reference_number == note.delivery_note_number,
            InventoryTransaction.transaction_type == "DISPATCH",
        )
    ).all()
    assert list(left_from) == [node_id], "the movement names the bin it left"


def test_the_warehouse_row_goes_first_and_the_bins_make_up_the_rest() -> None:
    """Three on the warehouse's own row, two bins: the row empties first."""
    session, firm, branch, warehouse, customer, product, actor = _world()
    first = _bin(session, warehouse, "B1")
    second = _bin(session, warehouse, "B2")
    places = {"firm": firm, "branch": branch, "warehouse": warehouse}
    _stock(session, product=product, quantity=Decimal("3"), **places)
    _into_bin(session, product=product, node_id=first, quantity="2", **places)
    _into_bin(session, product=product, node_id=second, quantity="5", **places)
    order, line = _approved_order(
        session,
        customer=customer,
        product=product,
        quantity=Decimal("6"),
        actor_id=actor,
        **places,
    )

    _dispatch(
        session,
        firm=firm,
        order=order,
        order_line=line,
        quantity=Decimal("6"),
        on=date(2026, 8, 4),
        actor_id=actor,
    )

    held = _held(session, product)
    assert held[None] == Decimal("0"), "the warehouse's own row went first"
    assert held[first] + held[second] == Decimal("4")
    assert line.reserved_quantity == Decimal("0")


def test_a_line_the_warehouse_row_covers_leaves_the_bins_alone() -> None:
    """Enough on the warehouse's own row: nothing is drawn from a bin."""
    session, firm, branch, warehouse, customer, product, actor = _world()
    node_id = _bin(session, warehouse, "B1")
    places = {"firm": firm, "branch": branch, "warehouse": warehouse}
    _stock(session, product=product, quantity=Decimal("5"), **places)
    _into_bin(session, product=product, node_id=node_id, quantity="4", **places)
    order, line = _approved_order(
        session,
        customer=customer,
        product=product,
        quantity=Decimal("5"),
        actor_id=actor,
        **places,
    )

    _dispatch(
        session,
        firm=firm,
        order=order,
        order_line=line,
        quantity=Decimal("5"),
        on=date(2026, 8, 4),
        actor_id=actor,
    )

    held = _held(session, product)
    assert held[None] == Decimal("0")
    assert held[node_id] == Decimal("4")


def test_a_refusal_says_what_stands_in_the_bins() -> None:
    """Four in a bin and six asked for: refused, naming the bin and the four."""
    session, firm, branch, warehouse, customer, product, actor = _world()
    node_id = _bin(session, warehouse, "B1")
    places = {"firm": firm, "branch": branch, "warehouse": warehouse}
    _into_bin(session, product=product, node_id=node_id, quantity="4", **places)
    order, line = _approved_order(
        session,
        customer=customer,
        product=product,
        quantity=Decimal("10"),
        actor_id=actor,
        **places,
    )

    with pytest.raises(ValidationError, match="4 in bin B1"):
        _dispatch(
            session,
            firm=firm,
            order=order,
            order_line=line,
            quantity=Decimal("6"),
            on=date(2026, 8, 4),
            actor_id=actor,
        )
    session.rollback()

    assert _held(session, product)[node_id] == Decimal("4"), "nothing moved"
