"""Recognise what an offer gave when a client sends a document back.

The offers' engine puts free goods on a sales order and a quotation: free
units on a line itself, or a line that sells nothing -- a gift, or the loose
pieces of a line sold by the box. Each such stored line names its offer in
``free_promotion_id``. A client that sends the document back as it read it
sends those as figures, and a figure sent is a figure typed, so the save has
to tell the echo from the typing (D-PRC-48).

It was told by **line number** alone, which holds only while no line moves.
Delete the line above, or insert one, and the echoed figures arrive at other
numbers: they stood as typed, named no offer and claimed nothing, and an
offer with a spent budget of 2 free units went on giving them (D-PRC-58).
The write schemas carry no line id, so a line that moved is recognised by
what the stored document says about it instead.
"""

from collections.abc import Iterable, Sequence
from decimal import Decimal
from typing import Protocol
from uuid import UUID

ZERO = Decimal("0")


class SentLine(Protocol):
    """What a line of the request says about its goods."""

    @property
    def line_number(self) -> int:
        """Return the number the line was sent at."""

    @property
    def product_id(self) -> UUID:
        """Return the product."""

    @property
    def quantity(self) -> Decimal:
        """Return the quantity charged for."""

    @property
    def free_quantity(self) -> Decimal | None:
        """Return the free quantity sent, None where nothing was said."""

    @property
    def sales_uom_id(self) -> UUID | None:
        """Return the unit the line is in, None for the stock unit."""


class StoredLine(Protocol):
    """What a stored line says about its goods and who gave the free ones."""

    line_number: int
    product_id: UUID
    quantity: Decimal
    free_quantity: Decimal
    free_promotion_id: UUID | None
    sales_uom_id: UUID | None


def _is_echo(item: SentLine, line: StoredLine, *, moved: bool) -> bool:
    """Say whether a sent line is the stored offer's line coming back.

    A line that sells nothing is the engine's own. At its own number it is
    that line whatever figure came with it; anywhere else it has to repeat
    the line's facts -- the free figure and the unit -- or it is a free line
    somebody typed. Free units on a line that sells something are the
    offer's only while the figure is still the offer's.
    """
    if line.quantity == ZERO:
        if item.quantity != ZERO:
            return False
        return not moved or (
            item.free_quantity == line.free_quantity
            and item.sales_uom_id in (None, line.sales_uom_id)
        )
    return (
        item.quantity > ZERO
        and item.free_quantity is not None
        and item.free_quantity == line.free_quantity
    )


def echoes_of_what_an_offer_gave[Stored: StoredLine](
    sent: Sequence[SentLine], stored: Iterable[Stored]
) -> dict[int, Stored]:
    """Match each sent line that echoes an offer's free goods to its stored line.

    Position first: a sent line of the same product and the same kind (one
    that sells something, or one that does not) at a stored line's number
    **is** that line, echoed or changed, and is judged against nothing else.
    Then the stored offer lines nothing stayed at are looked for by their
    facts among the sent lines that did not stay anywhere, each taken once.

    Args:
        sent: The request's lines, in the order sent.
        stored: The document's lines as they stand.

    Returns:
        The stored line each echo is of, keyed by its index in ``sent``. A
        line absent from it is the sender's own.

    """
    rows = sorted(stored, key=lambda line: line.line_number)
    if all(line.free_promotion_id is None for line in rows):
        return {}
    by_number = {line.line_number: line for line in rows}
    found: dict[int, Stored] = {}
    stayed: set[int] = set()
    kept_numbers: set[int] = set()
    for index, item in enumerate(sent):
        line = by_number.get(item.line_number)
        if (
            line is None
            or line.line_number in kept_numbers
            or line.product_id != item.product_id
            or (line.quantity == ZERO) != (item.quantity == ZERO)
        ):
            continue
        stayed.add(index)
        kept_numbers.add(line.line_number)
        if line.free_promotion_id is not None and _is_echo(item, line, moved=False):
            found[index] = line
    for index, item in enumerate(sent):
        if index in stayed:
            continue
        for line in rows:
            if (
                line.free_promotion_id is None
                or line.line_number in kept_numbers
                or line.product_id != item.product_id
                or not _is_echo(item, line, moved=True)
            ):
                continue
            kept_numbers.add(line.line_number)
            found[index] = line
            break
    return found
