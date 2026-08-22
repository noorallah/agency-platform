"""What a document line is discounted by, decided in one place.

Every sales and purchase service worked this out for itself, and they did not
agree. Quotations, sales orders, delivery notes, purchases and goods receipts
took `amount if amount > 0 else gross * percent / 100`; sales invoices, sales
returns, purchase invoices and purchase returns read the amount alone and
stored the percentage without ever looking at it. A ten percent order was
therefore invoiced at full price, with `discount_percent = 10` sitting on the
invoice line as a lie.

Three rules live here, and nowhere else:

**What was asked for wins over what was assumed.** An explicit amount beats an
explicit percentage, which beats the customer's standing discount. An explicit
zero is an instruction -- it is how somebody says "not this time" to a customer
who normally gets ten percent -- so `None` and `0` are different answers and the
schemas must keep them apart.

**The stored pair agrees with itself.** Where an amount is given, the percentage
recorded is the one that amount actually represents, rather than whatever the
caller also happened to send. A line that says 10% and 50.00 on a 1,000.00 line
is a line nobody can reconcile.

**A discount cannot exceed the line.** Only `goods_receipt` refused this; the
others produced a negative taxable value, which the tax helpers silently turned
into zero tax while the negative flowed on into the document total.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.core.exceptions import ValidationError
from app.core.utils.money import quantize_money

ZERO = Decimal("0")
HUNDRED = Decimal("100")


@dataclass(frozen=True, slots=True)
class LineDiscount:
    """What to take off a line, and the rate it represents."""

    amount: Decimal
    percent: Decimal

    #: Where it came from, for a caller that wants to say so on screen.
    source: str


def resolve_line_discount(
    *,
    gross: Decimal,
    percent: Decimal | None = None,
    amount: Decimal | None = None,
    customer_default: Decimal | None = None,
) -> LineDiscount:
    """Return the discount for one line.

    Args:
        gross: The line's value before discount -- quantity times price. Free
            goods are excluded from it everywhere, so they are never discounted.
        percent: The percentage the caller asked for, or None if they said
            nothing. Zero is an answer, not a silence.
        amount: The currency figure the caller asked for, or None.
        customer_default: The customer's standing discount, used only when the
            caller said nothing at all.

    Returns:
        The amount to deduct, the percentage it represents, and which of the
        three decided it.

    Raises:
        ValidationError: If the discount is negative, or larger than the line.

    """
    gross = quantize_money(gross)

    if amount is not None:
        applied = quantize_money(amount)
        source = "amount"
    elif percent is not None:
        applied = quantize_money(gross * quantize_money(percent) / HUNDRED)
        source = "percent"
    elif customer_default is not None and customer_default > ZERO:
        applied = quantize_money(gross * quantize_money(customer_default) / HUNDRED)
        source = "customer"
    else:
        return LineDiscount(amount=ZERO, percent=ZERO, source="none")

    if applied < ZERO:
        raise ValidationError("A discount cannot be negative.")
    if applied > gross:
        raise ValidationError("Discount cannot exceed the line amount.")

    # Derived rather than echoed, so the two figures on the line always agree.
    # A zero-value line has no rate to speak of; recording the asked-for
    # percentage there would divide by nothing.
    rate = (
        quantize_money(applied * HUNDRED / gross)
        if gross > ZERO
        else quantize_money(percent or customer_default or ZERO)
    )
    return LineDiscount(amount=applied, percent=rate, source=source)
