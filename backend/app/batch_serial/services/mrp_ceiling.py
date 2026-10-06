"""Nobody is charged more than the MRP printed on the batch they are sent.

The check lived on the bill alone (backlog 79 row 7), and a bill is the last
document of a sale: an order pinned to a batch at a price above its MRP was
saved and approved, its delivery note was dispatched, and only then was the
bill refused -- with the goods already out (D-PRC-7). The rule is the same
wherever a price meets a batch, so it is one function, with one wording:

- a sales order line saved with a pinned batch;
- a counter bill saved with the batches it chose, through the order it raises;
- a delivery note at dispatch, once each line knows the batches it draws
  from -- chosen by a person, carried by a serial, or allocated earliest
  expiry first -- and **before** any stock moves;
- the bill at approval, as before.

Where no batch is known yet -- an order line with no pin -- there is nothing
to compare with, and guessing the batch the allocator will choose later would
refuse an order for a batch it may never ship. Such a line is judged at
dispatch.

The MRP is printed per batch and includes tax, so a line is judged on what
each **charged** stock unit costs the customer: after its discounts, with its
tax, freight left out. Free goods charge nothing and are not counted. The
product's own MRP stands in for a batch that carries none, and a line drawn
from several batches is held to the lowest of them.

**The pack is a stock unit, and a line need not be.** A line sold by the box
of twelve charges a box, and the MRP is printed on a piece, so the judge is
handed the line as it stands -- what it charges, for how many of its own
unit -- with how many stock units one of that unit holds, and does the one
conversion itself. Each caller used to hand over stock units it had worked
out, and the bill worked them out wrongly: a box at 1,200.00, which is
112.00 a piece with tax and under an MRP of 120.00, passed the order and the
dispatch and was refused on the bill as "1344.00 a unit" with the goods
already out (D-PRC-36).
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.batch_serial.models import BatchRecord
from app.core.exceptions import ValidationError
from app.products.models import Product

ZERO = Decimal("0")
_PAISA = Decimal("0.01")


def refuse_above_batch_mrp(
    session: Session,
    *,
    line_number: int,
    product_id: UUID,
    batch_ids: Iterable[UUID | None],
    paid: Decimal,
    quantity: Decimal,
    stock_units_per_unit: Decimal | None = None,
) -> None:
    """Refuse a line charging more per unit than the MRP of a batch it ships.

    Args:
        session: The caller's unit of work; only read.
        line_number: The line, for the refusal.
        product_id: Whose MRP stands in for a batch with none.
        batch_ids: The batches the line leaves from; ``None`` entries -- stock
            held under no batch -- are ignored.
        paid: What the line costs the customer with tax, freight left out.
        quantity: How many that pays for, in the line's own unit, free goods
            left out.
        stock_units_per_unit: How many stock units one of the line's unit
            holds -- 12 for a box of twelve; one, or nothing, for a line in
            the stock unit.

    Raises:
        ValidationError: Naming the line, the rate and the MRP.

    """
    wanted = {batch_id for batch_id in batch_ids if batch_id is not None}
    charged = Decimal(str(quantity or 0)) * Decimal(str(stock_units_per_unit or 1))
    if not wanted or charged <= ZERO:
        return
    printed = dict(
        session.execute(
            select(BatchRecord.id, BatchRecord.mrp).where(BatchRecord.id.in_(wanted))
        )
        .tuples()
        .all()
    )
    fallback = session.scalar(select(Product.mrp).where(Product.id == product_id))
    ceilings = [
        Decimal(str(mrp))
        for mrp in (printed.get(batch_id) or fallback for batch_id in wanted)
        if mrp is not None and Decimal(str(mrp)) > ZERO
    ]
    if not ceilings:
        return
    rate = (Decimal(str(paid)) / charged).quantize(_PAISA)
    ceiling = min(ceilings)
    if rate > ceiling:
        raise ValidationError(
            f"Line {line_number}: charges {rate} a unit with tax, "
            f"above the MRP of {ceiling} printed on the batch it ships."
        )
