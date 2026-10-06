"""Quantities as a request states them.

One place for the reading of a quantity that more than one document's write
model has to agree on, so the buying and the selling return cannot read the
same line differently.
"""

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

_FOUR_PLACES = Decimal("0.0001")


def at_quantity_scale(value: Decimal | int | str | None) -> Decimal:
    """Return a quantity at the four places every quantity column holds.

    A quantity summed in SQL across a product of two columns comes back at
    the product's scale: one free unit an offer gave read
    ``1.00000000000000`` in its report and its budget, being 1.0000 times a
    ten-place factor (D-PRC-57).
    """
    number = Decimal(str(value if value is not None else 0))
    return number.quantize(_FOUR_PLACES, rounding=ROUND_HALF_UP)


def plain_quantity(value: Decimal | int | str | None) -> str:
    """Return a quantity as a message states it: no padding, no exponent.

    ``1.0000`` reads "1", ``0.5833`` reads "0.5833" and nothing reads "0" --
    one spelling, where refusals printed a nothing as ``0``, ``0.0000`` and
    ``1.00000000000000`` depending on which column it came off (D-PRC-57).
    """
    number = Decimal(str(value if value is not None else 0))
    if number == 0:
        return "0"
    return f"{number.normalize():f}"


def counted_in(figures: Sequence[Decimal], per_unit: Decimal) -> list[Decimal] | None:
    """Return figures counted in another unit, where they are whole in it.

    ``per_unit`` is how many of the figures' own unit make one of the other:
    twelve where pieces are to be read as boxes, a twelfth where boxes are to
    be read as pieces. A refusal that counts speaks the unit the person
    typed wherever every figure in the sentence is **the same quantity there
    at four places** -- 36, 12 and 48 pieces are 3, 1 and 4 BOX; 26 pieces
    are no number of boxes, and the sentence then stays where it is exact
    (D-PRC-62).

    A figure kept at four places in the larger unit was rounded on its way
    in -- thirteen pieces are stored as 1.0833 of a box -- so the whole
    number it was is tried first: 1.0833 BOX reads 13 PIECE, never 12.9996
    (D-PRC-86).

    Args:
        figures: The quantities, each in the same unit.
        per_unit: How many of that unit one of the other unit is.

    Returns:
        The figures in the other unit, or None where any one of them is not
        the same quantity there, or the factor says nothing.

    """
    if per_unit <= 0:
        return None
    counted: list[Decimal] = []
    for figure in figures:
        value = at_quantity_scale(figure)
        for candidate in (
            (value / per_unit).to_integral_value(rounding=ROUND_HALF_UP),
            at_quantity_scale(value / per_unit),
        ):
            if at_quantity_scale(candidate * per_unit) == value:
                counted.append(at_quantity_scale(candidate))
                break
        else:
            return None
    return counted


def free_goods_alone(data: object, *, quantity_field: str) -> object:
    """Read "0 charged, n free" as n going back, all of them free.

    A return line's quantity is everything on the line and ``free_quantity``
    is how many of those are free. The free units of a line that was all
    free -- an offer's own free line, a supplier scheme's -- are naturally
    typed the other way, as a quantity of 0 with 1 free, and that was refused
    on both returns (D-PRC-51). Such a line is restated here in the one shape
    the services read, the whole with its free part named, so there is no
    second path through either of them; how many free units may still go
    back is the service's cap, as before.

    Called from a ``model_validator(mode="before")``. Anything that is not a
    line of quantity 0 with a free quantity above 0 is returned untouched --
    including 0 with nothing free, which each document refuses in its own
    words.
    """
    if not isinstance(data, dict):
        return data
    try:
        quantity = Decimal(str(data.get(quantity_field)))
        free = Decimal(str(data.get("free_quantity") or 0))
    except ArithmeticError:
        # Not a number: the field's own validation says so.
        return data
    if quantity != 0 or free <= 0:
        return data
    return {**data, quantity_field: data["free_quantity"]}
