"""A lot's retail and wholesale prices, worked out from two margins (L3).

`docs/design/LOT_MARGINS_DESIGN.md`, sections 3.3 and 3.4. A firm costing by
lot gives every lot two prices before tax: retail, held in ``ptr``, and
wholesale, held in ``pts``. Each is the lot's cost per stock unit marked up by
a margin -- price = cost x (1 + margin / 100) -- kept to the paisa and never
rounded further, because rounding to the rupee belongs to the bill.

A price typed for a kind wins over its margin, and the margin is worked back
from it, so the lot can always say how its prices were reached. A kind with
neither a price nor a margin gives the lot no price of that kind, and a sale
from it falls through the ranking as it did before L3.

The prices are worked out once, when the lot is made. A later correction of
the lot's cost does not move them.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.products.models.product import Product

ZERO = Decimal("0")
HUNDRED = Decimal("100")
PAISA = Decimal("0.01")
#: The margin columns are Numeric(9,4); a margin worked back from a price
#: wildly off the cost is not kept rather than overflowing them.
_MARGIN_LIMIT = Decimal("100000")


@dataclass(frozen=True)
class LotPrices:
    """The two prices a lot carries and the margins that gave them."""

    ptr: Decimal | None = None
    pts: Decimal | None = None
    retail_margin_percent: Decimal | None = None
    wholesale_margin_percent: Decimal | None = None

    def within(self, mrp: Decimal | None) -> LotPrices:
        """Drop a price the lot register would refuse, for a lot nobody typed.

        Stock found at a count, a repack's output and opening stock with no
        price typed are priced by the margins alone; a worked price above the
        MRP before tax, or a wholesale price above the retail one, is left
        off the lot rather than refusing the movement that made it.
        """
        prices = self
        if mrp is not None:
            if prices.ptr is not None and prices.ptr > mrp:
                prices = replace(prices, ptr=None)
            if prices.pts is not None and prices.pts > mrp:
                prices = replace(prices, pts=None)
        if (
            prices.ptr is not None
            and prices.pts is not None
            and prices.pts > prices.ptr
        ):
            prices = replace(prices, pts=None)
        return prices


def worked_price(cost: Decimal, margin: Decimal) -> Decimal:
    """Return ``cost`` marked up by ``margin`` percent, to the paisa."""
    return (cost * (1 + margin / HUNDRED)).quantize(PAISA, rounding=ROUND_HALF_UP)


def margin_from_price(cost: Decimal | None, price: Decimal) -> Decimal | None:
    """Return the mark-up ``price`` makes on ``cost``, to two places.

    None where there is no cost to measure it on, or where the figure would
    not fit the column.
    """
    if cost is None or cost <= ZERO:
        return None
    margin = ((price / cost - 1) * HUNDRED).quantize(PAISA, rounding=ROUND_HALF_UP)
    return margin if abs(margin) < _MARGIN_LIMIT else None


def _one_kind(
    cost: Decimal | None, margin: Decimal | None, price: Decimal | None
) -> tuple[Decimal | None, Decimal | None]:
    """Work out one kind's price and margin: a typed price wins."""
    if price is not None:
        return price, margin_from_price(cost, price)
    if margin is None or cost is None or cost <= ZERO:
        return None, margin
    return worked_price(cost, margin), margin


def lot_prices(
    *,
    cost: Decimal | None,
    retail_margin_percent: Decimal | None,
    wholesale_margin_percent: Decimal | None,
    ptr: Decimal | None = None,
    pts: Decimal | None = None,
) -> LotPrices:
    """Work out a lot's two prices from its cost per stock unit before tax.

    Args:
        cost: What one stock unit cost before tax; None or zero works out
            no price (a free-only line has nothing to mark up).
        retail_margin_percent: The retail mark-up, None for none.
        wholesale_margin_percent: The wholesale mark-up, None for none.
        ptr: A retail price typed, which wins over the retail margin.
        pts: A wholesale price typed, which wins over the wholesale margin.

    Returns:
        The two prices and the margins they stand at.

    """
    retail, retail_margin = _one_kind(cost, retail_margin_percent, ptr)
    wholesale, wholesale_margin = _one_kind(cost, wholesale_margin_percent, pts)
    return LotPrices(
        ptr=retail,
        pts=wholesale,
        retail_margin_percent=retail_margin,
        wholesale_margin_percent=wholesale_margin,
    )


def product_margins(
    session: Session, product_id: UUID
) -> tuple[Decimal | None, Decimal | None]:
    """Return the product's retail and wholesale margins, None where unset."""
    product = session.get(Product, product_id)
    if product is None:
        return None, None
    return product.retail_margin_percent, product.wholesale_margin_percent


def mrp_warning(
    *,
    mrp: Decimal | None,
    ptr: Decimal | None,
    pts: Decimal | None,
    tax_rate: Decimal,
) -> str | None:
    """Say which of a lot's prices is above its MRP once tax is added.

    The MRP includes tax and the two prices do not, so a price at or below
    the MRP can still bill above it. That warns rather than refuses: the sale
    above the MRP is refused by the MRP ceiling, so nothing above it can be
    billed (`docs/design/LOT_MARGINS_DESIGN.md`, section 3.4). The sentence
    names the price that would sit exactly at the MRP.

    Args:
        mrp: The lot's MRP, with tax.
        ptr: The retail price, before tax.
        pts: The wholesale price, before tax.
        tax_rate: The line's tax as a fraction of its taxable value.

    Returns:
        The warning, or None where nothing is above the MRP.

    """
    if mrp is None:
        return None
    parts: list[str] = []
    for label, price in (("Retail price (PTR)", ptr), ("Wholesale price (PTS)", pts)):
        if price is None:
            continue
        with_tax = (price * (1 + tax_rate)).quantize(PAISA, rounding=ROUND_HALF_UP)
        if with_tax > mrp:
            at_mrp = (mrp / (1 + tax_rate)).quantize(PAISA, rounding=ROUND_DOWN)
            parts.append(
                f"{label} {price:.2f} is {with_tax:.2f} with tax, above the MRP "
                f"{mrp:.2f}; {at_mrp:.2f} before tax sits at the MRP."
            )
    return " ".join(parts) or None
