"""Promotional stock is given away, never sold at a price (BUY-1, A111)."""

from collections.abc import Iterable
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.products.models import Product


def assert_not_sold_at_a_price(
    session: Session,
    firm_id: UUID,
    lines: Iterable[tuple[UUID, Decimal | None]],
) -> None:
    """Refuse a price on any line whose product is for free issue only.

    A line at no price -- a free quantity, a free-product offer, a sample on a
    challan -- passes; one charging for promotional stock is refused, naming
    the products.

    Raises:
        ValidationError: Naming every free-issue product given a price.

    """
    priced = {product_id for product_id, price in lines if price and price > 0}
    if not priced:
        return
    names = list(
        session.scalars(
            select(Product.code).where(
                Product.firm_id == firm_id,
                Product.id.in_(priced),
                Product.free_issue_only.is_(True),
            )
        ).all()
    )
    if names:
        raise ValidationError(
            "Free-issue goods are given away, never sold at a price: "
            + ", ".join(sorted(names))
            + "."
        )
