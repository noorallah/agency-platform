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

And a line that **sells something** is not recognised by its number first
while another line of its product could be the one it echoes. Two lines of
one product, 24 with 2 free and 36 with 3, sent back in the other order were
each read as the other having stayed with a new figure typed on it: both
figures stood, no offer was named, nothing was claimed, and 10 free units
left against a budget of 5 (D-PRC-63). Such a line is paired with the stored
line whose **facts** it repeats, and its number only breaks a tie.
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


def _is_free_line_echo(item: SentLine, line: StoredLine) -> bool:
    """Say whether a moved line that sells nothing is the engine's own line.

    Away from its own number it has to repeat the line's facts -- the free
    figure and the unit -- or it is a free line somebody typed.
    """
    return item.free_quantity == line.free_quantity and item.sales_uom_id in (
        None,
        line.sales_uom_id,
    )


def _free_line_echoes[Stored: StoredLine](
    sent: Sequence[SentLine], rows: Sequence[Stored]
) -> dict[int, Stored]:
    """Match the sent lines that sell nothing to the stored ones that do not.

    Position first: a sent line of the same product at such a stored line's
    number **is** that line whatever figure came with it, and is judged
    against nothing else. Then the engine's lines nothing stayed at are
    looked for by their facts among the sent lines that did not stay
    anywhere, each taken once.
    """
    by_number = {line.line_number: line for line in rows}
    found: dict[int, Stored] = {}
    stayed: set[int] = set()
    kept_numbers: set[int] = set()
    for index, item in enumerate(sent):
        line = by_number.get(item.line_number)
        if (
            item.quantity != ZERO
            or line is None
            or line.line_number in kept_numbers
            or line.product_id != item.product_id
        ):
            continue
        stayed.add(index)
        kept_numbers.add(line.line_number)
        if line.free_promotion_id is not None:
            found[index] = line
    for index, item in enumerate(sent):
        if index in stayed or item.quantity != ZERO:
            continue
        for line in rows:
            if (
                line.free_promotion_id is None
                or line.line_number in kept_numbers
                or line.product_id != item.product_id
                or not _is_free_line_echo(item, line)
            ):
                continue
            kept_numbers.add(line.line_number)
            found[index] = line
            break
    return found


def _same_line(item: SentLine, line: StoredLine) -> bool:
    """Say whether the sent line is the stored one unchanged, where it stood."""
    return (
        item.line_number == line.line_number
        and item.quantity == line.quantity
        and item.free_quantity in (None, line.free_quantity)
    )


def _same_facts(item: SentLine, line: StoredLine) -> bool:
    """Say whether the sent line repeats the stored one's goods, wherever."""
    return item.quantity == line.quantity and item.free_quantity == line.free_quantity


def _same_figure_in_place(item: SentLine, line: StoredLine) -> bool:
    """Say whether the stored line's free figure came back at its number."""
    return (
        item.line_number == line.line_number
        and item.free_quantity == line.free_quantity
    )


def _silent_in_place(item: SentLine, line: StoredLine) -> bool:
    """Say whether the line stayed at its number, changed, with nothing said."""
    return item.line_number == line.line_number and item.free_quantity is None


def _same_figure(item: SentLine, line: StoredLine) -> bool:
    """Say whether the sent free figure is the one the stored line shows."""
    return item.free_quantity == line.free_quantity


#: How a sent line that sells something is recognised, surest reading first.
#: Each stored line is taken once, by the first sent line a rule pairs it
#: with, and a line paired by an earlier rule is out of the later ones.
_PAIRINGS = (
    _same_line,
    _same_facts,
    _same_figure_in_place,
    _silent_in_place,
    _same_figure,
)


def _selling_line_echoes[Stored: StoredLine](
    sent: Sequence[SentLine], rows: Sequence[Stored]
) -> dict[int, Stored]:
    """Pair the sent lines that sell something with the stored lines they echo.

    Per product, over **every** stored line of it that sells something: a
    line a person typed, or one sent back with nothing said about free
    goods, takes the stored line it is, so that line is not left for
    another's figure to be mistaken for. Only a figure sent, paired with a
    line an offer gave free units to, is reported as an echo.
    """
    selling = [line for line in rows if line.quantity > ZERO]
    paired: dict[int, Stored] = {}
    taken: set[int] = set()
    for rule in _PAIRINGS:
        for index, item in enumerate(sent):
            if index in paired or item.quantity <= ZERO:
                continue
            for line in selling:
                if (
                    line.line_number in taken
                    or line.product_id != item.product_id
                    or not rule(item, line)
                ):
                    continue
                taken.add(line.line_number)
                paired[index] = line
                break
    return {
        index: line
        for index, line in paired.items()
        if line.free_promotion_id is not None and sent[index].free_quantity is not None
    }


def echoes_of_what_an_offer_gave[Stored: StoredLine](
    sent: Sequence[SentLine], stored: Iterable[Stored]
) -> dict[int, Stored]:
    """Match each sent line that echoes an offer's free goods to its stored line.

    **A line that sells nothing** -- the engine's own -- is recognised by
    position first, then by its facts among the lines that moved
    (D-PRC-58).

    **A line that sells something** is paired, among the stored lines of its
    product, with the one whose facts it repeats, and position only breaks
    a tie (D-PRC-63): the same line where it stood; then the same quantity
    and free figure anywhere; then the same free figure at its own number (a
    quantity changed under the offer's figure); then a line at its own
    number that says nothing; then the same free figure on any line of the
    product not yet paired. Each stored line is taken once.

    The last rule is the doubtful one, and doubt goes to the offer: a figure
    typed on one line that equals what the offer gave another line of the
    same product, which itself came back changed or not at all, is read as
    that line's echo and the offer is worked out afresh. That can give the
    line less or more than was typed, and never more than the offer and its
    budget allow -- where standing as typed, on a wrong guess, gives free
    goods no offer names and no budget counts.

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
    free_lines = [line for line in rows if line.quantity == ZERO]
    return _free_line_echoes(sent, free_lines) | _selling_line_echoes(sent, rows)
