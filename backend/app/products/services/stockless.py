"""Which products are services: sold and billed, never held as stock.

Backlog §87 #3 (SG-3). Freight, repair, installation or any service is billed
with its SAC like any line, but there is nothing to reserve, pick, dispatch or
take back into a warehouse, and nothing left stock for cost of goods sold to
be about. The sales documents ask here, once per document, and skip the stock
half of each step for the lines named.

Decided as ERPNext treats a non-stock item rather than by refusing the line on
a delivery note: a service line **rides the same chain** -- order, note, bill,
return -- so the order's status, what is still to bill and what may be
returned are derived exactly as for goods, and only the stock is left out. A
firm that types delivery notes sees the service on the note as delivered work;
a counter bill raises the note for itself and nobody sees it.
"""

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.products.models import Product

#: The product types that never hold stock.
STOCKLESS_TYPES = frozenset({"SERVICE"})


def is_stockless(product: Product | None) -> bool:
    """Say whether a product is a service."""
    return product is not None and product.product_type in STOCKLESS_TYPES


def assert_held_as_stock(product: Product | None) -> None:
    """Refuse to bring a service into a warehouse.

    Opening stock, an adjustment upwards, a repack and a stock row made by
    hand each took a service and held it, valued, beside the goods
    (D-STK-71). Taking out what is already there is not refused: that is how
    a firm that has some gets rid of it.

    Raises:
        ValidationError: Naming the service.

    """
    if product is not None and is_stockless(product):
        raise ValidationError(
            f"{product.name} is a service, and a service is never held as "
            "stock. Bill it; there is nothing to bring into a warehouse."
        )


def stockless_products(session: Session, product_ids: Iterable[UUID]) -> set[UUID]:
    """Return which of these products are services, in one read.

    A document holds a page of lines, so the ids are few; an empty set asks
    nothing.
    """
    ids = {product_id for product_id in product_ids if product_id is not None}
    if not ids:
        return set()
    return set(
        session.scalars(
            select(Product.id).where(
                Product.id.in_(ids), Product.product_type.in_(STOCKLESS_TYPES)
            )
        ).all()
    )


__all__ = [
    "STOCKLESS_TYPES",
    "assert_held_as_stock",
    "is_stockless",
    "stockless_products",
]
