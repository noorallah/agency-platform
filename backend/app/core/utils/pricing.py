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
explicit percentage, which beats what the firm's price lists promise this
customer on this product, which beats the customer's blanket standing rate. An explicit
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
    price_list_percent: Decimal | None = None,
    customer_default: Decimal | None = None,
    subject: str = "the line amount",
) -> LineDiscount:
    """Return the discount for one line.

    Args:
        gross: The line's value before discount -- quantity times price. Free
            goods are excluded from it everywhere, so they are never discounted.
        percent: The percentage the caller asked for, or None if they said
            nothing. Zero is an answer, not a silence.
        amount: The currency figure the caller asked for, or None.
        price_list_percent: What the firm's price lists promise this customer
            on this product, or None where no list mentions it. Ranked above
            the blanket rate because it is the more specific arrangement, and
            below anything typed because a person deciding beats a table.
        customer_default: The customer's standing discount, used only when
            nothing more specific applies.
        subject: What the refusal calls the thing the discount cannot exceed.
            The same rule serves a line and a whole document, and a message
            naming the wrong one sends the reader looking in the wrong place.

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
    elif price_list_percent is not None:
        # A list that names the product at zero is an arrangement too, so this
        # branch is taken on `is not None` rather than on being positive --
        # unlike the blanket rate below, where zero has always meant "none set".
        applied = quantize_money(gross * quantize_money(price_list_percent) / HUNDRED)
        source = "price_list"
    elif customer_default is not None and customer_default > ZERO:
        applied = quantize_money(gross * quantize_money(customer_default) / HUNDRED)
        source = "customer"
    else:
        return LineDiscount(amount=ZERO, percent=ZERO, source="none")

    if applied < ZERO:
        raise ValidationError("A discount cannot be negative.")
    if applied > gross:
        raise ValidationError(f"Discount cannot exceed {subject}.")

    # Derived rather than echoed, so the two figures on the line always agree.
    # A zero-value line has no rate to speak of; recording the asked-for
    # percentage there would divide by nothing.
    rate = (
        quantize_money(applied * HUNDRED / gross)
        if gross > ZERO
        else quantize_money(percent or price_list_percent or customer_default or ZERO)
    )
    return LineDiscount(amount=applied, percent=rate, source=source)


def resolve_bill_discount(
    *,
    taxable: Decimal,
    percent: Decimal | None = None,
    amount: Decimal | None = None,
) -> LineDiscount:
    """Return the discount taken off a whole document.

    Same precedence as a line: what was typed in currency beats a rate, and the
    rate recorded is derived from the amount applied so the pair on the header
    agrees with itself.

    Args:
        taxable: What the lines come to after their own discounts. The bill
            discount comes off this, never off the gross, or two discounts
            would each be computed as though the other had not happened.
        percent: The rate asked for, or None.
        amount: The currency figure asked for, or None.

    Returns:
        The amount to take off the document and the rate it represents.

    Raises:
        ValidationError: If it is negative, or larger than the document.

    """
    return resolve_line_discount(
        gross=taxable,
        percent=percent,
        amount=amount,
        subject="what the lines come to",
    )


def apportion(total: Decimal, weights: list[Decimal]) -> list[Decimal]:
    """Split one figure across lines in proportion to their value.

    A discount on the whole bill has to reach the individual lines, because tax
    is charged per line and a document-level deduction that never touches a
    taxable value reduces no tax -- which is what ``header_discount_amount``
    does on a purchase order, deliberately not copied here.

    Rounding is the whole difficulty. Quantising each share independently
    leaves a residual of a few paise that belongs to nobody, and a document
    whose lines do not sum to its own total is one no reconciliation can
    accept. The residual is given to the **largest** line, where it is the
    smallest proportional distortion and where a paisa is least likely to
    change a rate anybody reads.

    Args:
        total: The figure to split. Zero returns zeros.
        weights: What each line is worth. Lines worth nothing get nothing;
            if every line is worth nothing there is nothing to split against,
            and the whole figure goes to the first line rather than vanishing.

    Returns:
        One share per weight, summing exactly to ``total``.

    """
    if not weights:
        return []
    total = quantize_money(total)
    if total == ZERO:
        return [ZERO for _ in weights]

    basis = sum(weights, ZERO)
    if basis <= ZERO:
        return [total] + [ZERO for _ in weights[1:]]

    shares = [quantize_money(total * weight / basis) for weight in weights]
    residual = total - sum(shares, ZERO)
    if residual != ZERO:
        largest = max(range(len(weights)), key=lambda index: weights[index])
        shares[largest] = quantize_money(shares[largest] + residual)
    return shares
