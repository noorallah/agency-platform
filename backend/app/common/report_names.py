"""Name the ids a report row carries, one read per table.

A register answers ids -- ``customer_id``, ``vendor_id``, ``branch_id``,
``warehouse_id`` -- and the desktop grid derives its columns from the row, so
a register that carries only ids shows a screen of UUIDs (D-RPT-17). Every
report that wants a name resolves it here.

The rule these helpers exist to keep is **one read per table per report**:
a name looked up inside the row loop is one query per row, which is how the
sales-order by-customer report came to open a connection per order
(D-RPT-19). Collect the ids first, call once, then build the rows.

``users`` lives only in the platform schema, so :func:`salesman_names` reads
it through ``platform_reader()``. A tenant session raises ``UndefinedTable``
for every firm outside the platform store, and SQLite keeps every table in one
schema, so the unit suite can never see that on its own.
"""

from collections.abc import Iterable
from typing import Any
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.branches.models import Branch, Warehouse
from app.common.firm_metadata import platform_reader
from app.customers.models import Customer
from app.identity.models import User
from app.products.models import Product
from app.sales.models import SalesTerritoryNode
from app.vendors.models import Vendor

__all__ = [
    "branch_names",
    "customer_names",
    "product_names",
    "salesman_names",
    "territory_names",
    "vendor_names",
    "warehouse_names",
]


def _wanted(ids: Iterable[UUID | None]) -> list[UUID]:
    """Return the ids worth reading: distinct, and never ``None``."""
    return list({value for value in ids if value is not None})


def _labels(
    session: Session, statement: Select[Any], ids: list[UUID]
) -> dict[UUID, str]:
    """Run one ``IN (...)`` read and key the labels it returns by id."""
    if not ids:
        return {}
    return {row[0]: row[1] for row in session.execute(statement).all()}


def customer_names(session: Session, ids: Iterable[UUID | None]) -> dict[UUID, str]:
    """Name each customer by ``display_name``, in one read.

    ``display_name`` is what every other screen shows and what the customer
    was told their account is called; ``name`` is the legal name and differs
    for most trading businesses (D-RPT-19).
    """
    wanted = _wanted(ids)
    return _labels(
        session,
        select(Customer.id, Customer.display_name).where(Customer.id.in_(wanted)),
        wanted,
    )


def vendor_names(session: Session, ids: Iterable[UUID | None]) -> dict[UUID, str]:
    """Name each supplier by ``display_name``, in one read."""
    wanted = _wanted(ids)
    return _labels(
        session,
        select(Vendor.id, Vendor.display_name).where(Vendor.id.in_(wanted)),
        wanted,
    )


def branch_names(session: Session, ids: Iterable[UUID | None]) -> dict[UUID, str]:
    """Name each branch, in one read."""
    wanted = _wanted(ids)
    return _labels(
        session,
        select(Branch.id, Branch.name).where(Branch.id.in_(wanted)),
        wanted,
    )


def warehouse_names(session: Session, ids: Iterable[UUID | None]) -> dict[UUID, str]:
    """Name each warehouse, in one read."""
    wanted = _wanted(ids)
    return _labels(
        session,
        select(Warehouse.id, Warehouse.name).where(Warehouse.id.in_(wanted)),
        wanted,
    )


def territory_names(session: Session, ids: Iterable[UUID | None]) -> dict[UUID, str]:
    """Name each territory node, in one read."""
    wanted = _wanted(ids)
    return _labels(
        session,
        select(SalesTerritoryNode.id, SalesTerritoryNode.name).where(
            SalesTerritoryNode.id.in_(wanted)
        ),
        wanted,
    )


def product_names(
    session: Session, ids: Iterable[UUID | None]
) -> dict[UUID, tuple[str, str]]:
    """Return ``(code, name)`` per product, in one read.

    Soft-deleted products are included deliberately: a report line names what
    was traded, and a product retired since still has to be nameable on the
    document that moved it.
    """
    wanted = _wanted(ids)
    if not wanted:
        return {}
    return {
        row[0]: (row[1], row[2])
        for row in session.execute(
            select(Product.id, Product.code, Product.name).where(Product.id.in_(wanted))
        ).all()
    }


def salesman_names(session: Session, ids: Iterable[UUID | None]) -> dict[UUID, str]:
    """Name each salesperson, in one read against the store holding ``users``.

    ``users`` is a platform table, so on PostgreSQL a firm-owned session
    cannot see it and the report answers 503. SQLite keeps one schema, so the
    request session is read there and the unit suite stays able to assert the
    names.
    """
    wanted = _wanted(ids)
    if not wanted:
        return {}
    statement = select(User.id, User.full_name).where(User.id.in_(wanted))
    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        rows = list(session.execute(statement).all())
    else:
        with platform_reader() as reader:
            rows = list(reader.execute(statement).all())
    return {row[0]: row[1] for row in rows}
