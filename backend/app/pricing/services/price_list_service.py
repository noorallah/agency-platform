"""Resolving which rate a customer has been promised on a product.

The rule this module exists to answer: given a firm, a customer, a product and
a date, what percentage comes off the line?

**The most specific arrangement wins.** A list naming the customer beats one
naming their territory, which beats the firm's own standing list. Within one
level of specificity the list that started most recently wins, because that is
the one somebody agreed last -- ranked explicitly rather than left to NULL
ordering, which sorts differently on PostgreSQL and SQLite and has produced a
defect here before.

Where a price list says nothing, `customers.default_discount_percent` still
applies: the list is more specific, not a replacement for the blanket rate.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, case, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.pricing.models import PriceList, PriceListItem

ZERO = Decimal("0")


class PriceListResolver:
    """Answer what a customer pays off a product, per the firm's price lists.

    Built once per document rather than per line: the lists that could apply
    depend on the customer, the territory and the date, none of which change
    between lines, so resolving them once and matching products against the
    result keeps a hundred-line invoice to one query.
    """

    def __init__(
        self,
        session: Session,
        *,
        firm_id: UUID,
        customer_id: UUID | None,
        territory_id: UUID | None,
        on: date,
    ) -> None:
        """Load the applicable rates for one document."""
        self._rates: dict[UUID, Decimal] = {}
        # No early exit for a document naming neither a customer nor a
        # territory: the firm's own standing list still applies to it.
        self._load(
            session,
            firm_id=firm_id,
            customer_id=customer_id,
            territory_id=territory_id,
            on=on,
        )

    def _load(
        self,
        session: Session,
        *,
        firm_id: UUID,
        customer_id: UUID | None,
        territory_id: UUID | None,
        on: date,
    ) -> None:
        """Read every rate that could apply, most specific last.

        Ordered so that writing each row into a dict leaves the most specific
        arrangement in place: firm-wide first, then territory, then customer.
        A later write wins, which is the whole ranking expressed once.
        """
        scope: list[ColumnElement[bool]] = [
            and_(PriceList.customer_id.is_(None), PriceList.territory_id.is_(None))
        ]
        if territory_id is not None:
            scope.append(PriceList.territory_id == territory_id)
        if customer_id is not None:
            scope.append(PriceList.customer_id == customer_id)

        # 0 firm-wide, 1 territory, 2 customer. Ranked explicitly rather than
        # relying on how NULLs sort: PostgreSQL puts them first in DESC and
        # SQLite last, which is exactly how a firm-wide UOM rule once outranked
        # a product's own factor in production while the tests stayed green.
        specificity = case(
            (PriceList.customer_id.isnot(None), 2),
            (PriceList.territory_id.isnot(None), 1),
            else_=0,
        )

        rows = session.execute(
            select(PriceListItem.product_id, PriceListItem.discount_percent)
            .join(PriceList, PriceList.id == PriceListItem.price_list_id)
            .where(
                PriceList.firm_id == firm_id,
                PriceList.is_deleted.is_(False),
                PriceList.status == "ACTIVE",
                PriceList.effective_from <= on,
                or_(PriceList.effective_to.is_(None), PriceList.effective_to >= on),
                or_(*scope),
                PriceListItem.is_deleted.is_(False),
            )
            .order_by(specificity.asc(), PriceList.effective_from.asc())
        ).all()

        for product_id, percent in rows:
            self._rates[product_id] = Decimal(str(percent))

    def rate_for(self, product_id: UUID | None) -> Decimal | None:
        """Return the promised rate, or None where no list mentions the product.

        None rather than zero, and the distinction carries weight: a product no
        list mentions falls through to the customer's blanket rate, where a
        product a list deliberately puts at zero does not.
        """
        if product_id is None:
            return None
        return self._rates.get(product_id)
