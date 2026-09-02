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
        # Each product's whole ladder: (quantity the rate starts at, rate),
        # ascending. A product with no breaks has one entry starting at zero.
        self._rates: dict[UUID, list[tuple[Decimal, Decimal]]] = {}
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
            select(
                PriceListItem.product_id,
                PriceListItem.min_quantity,
                PriceListItem.discount_percent,
                specificity.label("rank"),
            )
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
            .order_by(
                specificity.asc(),
                PriceList.effective_from.asc(),
                PriceListItem.min_quantity.asc(),
            )
        ).all()

        # Each product keeps its whole ladder, ordered by the quantity the
        # rate starts at. A more specific list replaces the ladder rather than
        # merging into it: a customer's own arrangement is the arrangement,
        # not an amendment to the firm-wide one.
        ladders: dict[UUID, dict[Decimal, Decimal]] = {}
        seen: dict[UUID, int] = {}
        for product_id, min_quantity, percent, rank in rows:
            if seen.get(product_id) != rank:
                seen[product_id] = rank
                ladders[product_id] = {}
            ladders[product_id][Decimal(str(min_quantity))] = Decimal(str(percent))
        for product_id, ladder in ladders.items():
            self._rates[product_id] = sorted(ladder.items())

    def rate_for(
        self, product_id: UUID | None, quantity: Decimal | None = None
    ) -> Decimal | None:
        """Return the promised rate, or None where no list mentions the product.

        None rather than zero, and the distinction carries weight: a product no
        list mentions falls through to the customer's blanket rate, where a
        product a list deliberately puts at zero does not.

        Where a list holds quantity breaks, the **highest break at or below the
        line's quantity** wins: breaks of 0, 50 and 200 price a line of 120 at
        the 50. A caller that says nothing about quantity gets the ordinary
        rate, which is what every list held before breaks existed.
        """
        if product_id is None:
            return None
        breaks = self._rates.get(product_id)
        if not breaks:
            return None
        wanted = Decimal(str(quantity)) if quantity is not None else ZERO
        best: Decimal | None = None
        for threshold, percent in breaks:
            if threshold <= wanted:
                best = percent
            else:
                # Sorted ascending, so the first break above the quantity ends
                # it -- nothing further down can apply either.
                break
        return best
