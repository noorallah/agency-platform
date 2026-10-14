"""Cost and margin on a sales order or bill line, for the screen only.

L3 step 4 (``docs/design/LOT_MARGINS_DESIGN.md`` section 3.7). Each line of an
order and of a bill says what its goods cost and what it earns over that cost,
and the document says the same in total, so whoever bills sees the margin
before the bill goes out.

**What the cost is.** A bill line whose goods have left carries its own
``cost_amount``, written at dispatch from the lots its delivery note line took.
Before that, and on every order line, the cost is worked out the way the price
floor judges a line (``PriceFloorService.unit_costs``): the lots the line takes
where all are known on a firm costing by lot (a pinned batch, or the lots its
delivery note line chose), else the item's moving average, else its purchase
price -- times every unit that leaves, free goods included, since they cost the
firm as much as the charged ones. Such a cost is flagged ``cost_is_estimate``.

**What the margin is.** The line's taxable value (``net_amount`` less
``tax_amount``: after its own discount, its share of the bill discount and of
freight) less its cost, and that as a percentage of the cost. None where the
cost is unknown; the percentage is None where the cost is nothing.

**Who sees it.** Only a holder of ``PRODUCT_VIEW_COST_PRICE``: the routers
pass ``show_cost`` and nothing here runs without it. **Never printed**: no
print service reads these fields, and
``tests/unit/test_line_margin.py`` fails the build if one does.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.utils.money import quantize_money
from app.sales_order.services.price_floor import (
    PricedLine,
    PriceFloorService,
    invoice_lines,
    order_lines,
)

_ZERO = Decimal("0")
_PERCENT = Decimal("0.01")


class _CostedLine(Protocol):
    """A line response that can be given its cost and margin."""

    free_quantity: Decimal
    conversion_factor: Decimal
    net_amount: Decimal
    tax_amount: Decimal
    cost_amount: Decimal | None
    cost_is_estimate: bool
    margin_amount: Decimal | None
    margin_percent: Decimal | None


class _CostedDocument(Protocol):
    """A document response that can be given its cost and margin in total."""

    cost_total: Decimal | None
    margin_total: Decimal | None


@dataclass(frozen=True, slots=True)
class LineMargin:
    """What one line's goods cost and what the line earns over that."""

    cost_amount: Decimal | None
    cost_is_estimate: bool
    margin_amount: Decimal | None
    margin_percent: Decimal | None


def margin_of(taxable: Decimal, cost: Decimal | None, *, estimate: bool) -> LineMargin:
    """Return a line's margin over its cost; nothing where the cost is unknown."""
    if cost is None:
        return LineMargin(None, False, None, None)
    cost = quantize_money(cost)
    margin = quantize_money(Decimal(taxable) - cost)
    percent = (
        (margin * Decimal("100") / cost).quantize(_PERCENT) if cost > _ZERO else None
    )
    return LineMargin(cost, estimate, margin, percent)


def _apply(
    session: Session,
    firm_id: UUID,
    lines: Sequence[_CostedLine],
    priced: Sequence[PricedLine],
    stored: Sequence[Decimal | None],
) -> None:
    """Give each line its cost and margin, estimating where none is stored."""
    wanted = [line for line, cost in zip(priced, stored, strict=True) if cost is None]
    units = PriceFloorService(session).unit_costs(firm_id, wanted) if wanted else {}
    for line, price_line, cost in zip(lines, priced, stored, strict=True):
        estimate = cost is None
        if estimate:
            unit = units.get(price_line)
            free = Decimal(line.free_quantity or _ZERO) * Decimal(
                line.conversion_factor or Decimal("1")
            )
            cost = None if unit is None else unit * (price_line.stock_quantity + free)
        taxable = Decimal(line.net_amount) - Decimal(line.tax_amount)
        found = margin_of(taxable, cost, estimate=estimate)
        line.cost_amount = found.cost_amount
        line.cost_is_estimate = found.cost_is_estimate
        line.margin_amount = found.margin_amount
        line.margin_percent = found.margin_percent


def _total(document: _CostedDocument, lines: Sequence[_CostedLine]) -> None:
    """Total the lines' cost and margin; nothing where any line has no cost."""
    if not lines or any(line.cost_amount is None for line in lines):
        return
    document.cost_total = sum(
        (Decimal(line.cost_amount or _ZERO) for line in lines), _ZERO
    )
    document.margin_total = sum(
        (Decimal(line.margin_amount or _ZERO) for line in lines), _ZERO
    )


def cost_order_lines(
    session: Session,
    firm_id: UUID,
    documents: Sequence[tuple[_CostedDocument, Sequence[_CostedLine]]],
) -> None:
    """Give a page of sales orders their lines' cost and margin, and totals.

    An order line never stores a cost: the goods have not left, so every
    cost here is an estimate (the pinned lot's, else the average's).
    """
    every = [line for _, lines in documents for line in lines]
    _apply(session, firm_id, every, order_lines(every), [None] * len(every))
    for document, lines in documents:
        _total(document, lines)


def cost_invoice_lines(
    session: Session,
    firm_id: UUID,
    documents: Sequence[tuple[_CostedDocument, Sequence[_CostedLine]]],
) -> None:
    """Give a page of bills their lines' cost and margin, and totals.

    A line whose goods have left keeps the cost written at dispatch; the
    rest are estimated from the lots chosen, else the average.
    """
    every = [line for _, lines in documents for line in lines]
    _apply(
        session,
        firm_id,
        every,
        invoice_lines(every),
        [line.cost_amount for line in every],
    )
    for document, lines in documents:
        _total(document, lines)
