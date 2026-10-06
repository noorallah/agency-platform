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
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import and_, case, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.pricing.models import PriceList, PriceListItem

ZERO = Decimal("0")
_FOUR_PLACES = Decimal("0.0001")


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
        # The fixed price (SEL-9) each break carries, where the list names one.
        self._prices: dict[UUID, list[tuple[Decimal, Decimal | None]]] = {}
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
                PriceListItem.rate,
            )
            .join(PriceList, PriceList.id == PriceListItem.price_list_id)
            .where(
                PriceList.firm_id == firm_id,
                PriceList.is_deleted.is_(False),
                PriceList.status == "ACTIVE",
                PriceList.effective_from <= on,
                or_(PriceList.effective_to.is_(None), PriceList.effective_to >= on),
                or_(*scope),
                # A supplier's list prices purchases, never a sale (BUY-3).
                PriceList.vendor_id.is_(None),
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
        prices: dict[UUID, dict[Decimal, Decimal | None]] = {}
        seen: dict[UUID, int] = {}
        for product_id, min_quantity, percent, rank, rate in rows:
            if seen.get(product_id) != rank:
                seen[product_id] = rank
                ladders[product_id] = {}
                prices[product_id] = {}
            threshold = Decimal(str(min_quantity))
            ladders[product_id][threshold] = Decimal(str(percent))
            prices[product_id][threshold] = None if rate is None else Decimal(str(rate))
        for product_id, ladder in ladders.items():
            self._rates[product_id] = sorted(ladder.items())
            self._prices[product_id] = sorted(prices[product_id].items())

    def mentions(self, product_id: UUID | None) -> bool:
        """Say whether any list in force holds a rate for the product."""
        return product_id is not None and bool(self._rates.get(product_id))

    @staticmethod
    def _asked_at(quantity: Decimal | None) -> Decimal:
        """Return the stock quantity a break is asked at, at four places.

        A quantity is kept to four places and a break is written to four,
        so the question is asked at four. The caller's figure is a typed
        quantity times a conversion factor, and a factor that runs from a
        small unit to a large one cannot be written exactly: a piece is
        0.0833333333 of a box of twelve, 24 pieces came to 1.9999999992
        boxes, and a line the document itself counts as 2.0000 boxes missed
        the break "from 2" (D-PRC-52). Rounded here, in the one place both
        ladders are read, whichever way a line's factor runs.
        """
        if quantity is None:
            return ZERO
        return Decimal(str(quantity)).quantize(_FOUR_PLACES, rounding=ROUND_HALF_UP)

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

        **The quantity is in stock units**, as ``price_for``'s is: a list
        names no unit, so its breaks count the unit the product is kept in,
        and a caller with a line in another unit multiplies by the line's
        factor first (`UomService.stock_factor`). 2 BOX of 12 reach a break
        "from 20"; asked at the typed 2 they took the fixed rate of the
        break at 20 and the discount of the break at 0.
        """
        if product_id is None:
            return None
        breaks = self._rates.get(product_id)
        if not breaks:
            return None
        wanted = self._asked_at(quantity)
        best: Decimal | None = None
        for threshold, percent in breaks:
            if threshold <= wanted:
                best = percent
            else:
                # Sorted ascending, so the first break above the quantity ends
                # it -- nothing further down can apply either.
                break
        return best

    def price_for(
        self, product_id: UUID | None, quantity: Decimal | None = None
    ) -> Decimal | None:
        """Return the fixed price a list agreed, at the break the quantity takes.

        The same break ``rate_for`` takes; None where the list names no price
        there, so the line falls through to the customer's level (SEL-9).
        """
        if product_id is None:
            return None
        breaks = self._prices.get(product_id)
        if not breaks:
            return None
        wanted = self._asked_at(quantity)
        best: Decimal | None = None
        for threshold, price in breaks:
            if threshold <= wanted:
                best = price
            else:
                break
        return best


class SupplierPriceResolver(PriceListResolver):
    """What the firm buys a product at from one supplier (BUY-3, A97).

    The supplier's own lists -- ``price_lists.vendor_id`` -- live on the
    date, with the same quantity breaks, fixed rates and "latest list wins"
    as the sales side. Built once per purchase document.
    """

    def __init__(
        self, session: Session, *, firm_id: UUID, vendor_id: UUID, on: date
    ) -> None:
        """Load the supplier's live rates for one document."""
        self._rates = {}
        self._prices = {}
        rows = session.execute(
            select(
                PriceListItem.product_id,
                PriceListItem.min_quantity,
                PriceListItem.discount_percent,
                PriceListItem.rate,
            )
            .join(PriceList, PriceList.id == PriceListItem.price_list_id)
            .where(
                PriceList.firm_id == firm_id,
                PriceList.vendor_id == vendor_id,
                PriceList.is_deleted.is_(False),
                PriceList.status == "ACTIVE",
                PriceList.effective_from <= on,
                or_(PriceList.effective_to.is_(None), PriceList.effective_to >= on),
                PriceListItem.is_deleted.is_(False),
            )
            .order_by(PriceList.effective_from.asc(), PriceListItem.min_quantity.asc())
        ).all()
        ladders: dict[UUID, dict[Decimal, Decimal]] = {}
        prices: dict[UUID, dict[Decimal, Decimal | None]] = {}
        for product_id, min_quantity, percent, rate in rows:
            threshold = Decimal(str(min_quantity))
            ladders.setdefault(product_id, {})[threshold] = Decimal(str(percent))
            prices.setdefault(product_id, {})[threshold] = (
                None if rate is None else Decimal(str(rate))
            )
        for product_id, ladder in ladders.items():
            self._rates[product_id] = sorted(ladder.items())
            self._prices[product_id] = sorted(prices[product_id].items())
