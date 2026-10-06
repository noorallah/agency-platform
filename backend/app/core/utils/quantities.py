"""Quantities as a request states them.

One place for the reading of a quantity that more than one document's write
model has to agree on, so the buying and the selling return cannot read the
same line differently.
"""

from decimal import Decimal


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
