"""Shared monetary rounding for transactional documents.

Every transactional module carried its own ``_q`` helper, and they did not agree.
Six quantized with ``ROUND_HALF_UP``; ``goods_receipt`` passed no rounding
argument at all, so it silently used Python's default ``ROUND_HALF_EVEN`` and
rounded goods-receipt money differently from every other document in the system.
Two of the six also rejected anything that was not already a ``Decimal``.

**Scale is four decimal places.** Money columns across the transactional modules
are ``Numeric(18, 4)``, chosen so unit prices, tax components and per-line
discounts survive without a second rounding step. ``MONEY_SCALE`` is the single
place that decision is recorded; the unused ``core.database.types.decimal_type``
default of ``(18, 2)`` never matched the schema and never applied to any column.
"""

from decimal import ROUND_HALF_UP, Decimal

MONEY_SCALE = Decimal("0.0001")
ZERO = Decimal("0")


def quantize_money(value: Decimal | int | str | None) -> Decimal:
    """Round a monetary amount to the storage scale, half away from zero.

    Args:
        value: The amount to round. ``None`` is treated as zero so callers can
            pass optional columns directly. Strings and ints are converted via
            ``str`` so binary floating point never enters the calculation.

    Returns:
        The amount quantized to ``MONEY_SCALE`` using ``ROUND_HALF_UP``.

    """
    if value is None:
        return ZERO
    return Decimal(str(value)).quantize(MONEY_SCALE, rounding=ROUND_HALF_UP)
