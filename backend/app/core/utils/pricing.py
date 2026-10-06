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
explicit percentage, which beats what the firm's promotions earned this line,
which beats what the firm's price lists promise this customer on this product,
which beats the customer's blanket standing rate, which beats whatever their
segment is normally given. An explicit
zero is an instruction -- it is how somebody says "not this time" to a customer
who normally gets ten percent -- so `None` and `0` are different answers and the
schemas must keep them apart.

A promotion sits below anything typed and above the standing arrangements for
the same reason each of those is where it is: a person deciding beats a rule,
and an offer the firm is running today is more specific than a list agreed once.

**The stored pair agrees with itself.** Where an amount is given, the percentage
recorded is the one that amount actually represents, rather than whatever the
caller also happened to send. A line that says 10% and 50.00 on a 1,000.00 line
is a line nobody can reconcile.

**A discount cannot exceed the line.** Only `goods_receipt` refused this; the
others produced a negative taxable value, which the tax helpers silently turned
into zero tax while the negative flowed on into the document total.
"""

from collections.abc import Callable
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
    promotion_amount: Decimal | None = None,
    price_list_percent: Decimal | None = None,
    customer_default: Decimal | None = None,
    customer_group_default: Decimal | None = None,
    subject: str = "the line amount",
) -> LineDiscount:
    """Return the discount for one line.

    Args:
        gross: The line's value before discount -- quantity times price. Free
            goods are excluded from it everywhere, so they are never discounted.
        percent: The percentage the caller asked for, or None if they said
            nothing. Zero is an answer, not a silence.
        amount: The currency figure the caller asked for, or None.
        promotion_amount: What the firm's promotions earned this line, already
            stacked and compounded by the promotion engine, or None where none
            applied. Ranked below anything typed, for the same reason the price
            list is -- a person deciding beats a rule -- and above the price
            list, because an offer the firm is running now is more specific
            than a standing arrangement.
        price_list_percent: What the firm's price lists promise this customer
            on this product, or None where no list mentions it. Ranked above
            the blanket rate because it is the more specific arrangement, and
            below anything typed because a person deciding beats a table.
        customer_default: The customer's standing discount, used only when
            nothing more specific applies.
        customer_group_default: What the customer's segment is normally given.
            Last of all, because a rate agreed with one shop is more specific
            than one agreed with a whole segment of them.
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
    elif promotion_amount is not None:
        applied = quantize_money(promotion_amount)
        source = "promotion"
    elif price_list_percent is not None:
        # A list that names the product at zero is an arrangement too, so this
        # branch is taken on `is not None` rather than on being positive --
        # unlike the blanket rate below, where zero has always meant "none set".
        applied = quantize_money(gross * quantize_money(price_list_percent) / HUNDRED)
        source = "price_list"
    elif customer_default is not None and customer_default > ZERO:
        applied = quantize_money(gross * quantize_money(customer_default) / HUNDRED)
        source = "customer"
    elif customer_group_default is not None and customer_group_default > ZERO:
        # Zero means "no arrangement" here too, exactly as it does one line up:
        # a segment with no agreed rate is not a segment agreeing on nothing.
        applied = quantize_money(
            gross * quantize_money(customer_group_default) / HUNDRED
        )
        source = "customer_group"
    else:
        return LineDiscount(amount=ZERO, percent=ZERO, source="none")

    if applied < ZERO:
        raise ValidationError("A discount cannot be negative.")
    if applied > gross:
        raise ValidationError(f"Discount cannot exceed {subject}.")

    # Derived rather than echoed, so the two figures on the line always agree.
    # A zero-value line has nothing to derive from, so the rate that decided it
    # stands -- and it is read from the branch that was actually taken rather
    # than from a chain of `or`s.
    #
    # `percent or price_list_percent or customer_default or ...` is falsy for
    # an explicit **zero**, so a line that had *refused* every arrangement fell
    # through and recorded the customer's standing rate beside an amount of
    # nothing. A gift line is the shape that makes it visible: a bill for
    # nothing printing "7.5% discount". Zero is an answer here exactly as it is
    # everywhere else in this function.
    asked = {
        "percent": percent,
        "price_list": price_list_percent,
        "customer": customer_default,
        "customer_group": customer_group_default,
    }.get(source)
    rate = (
        quantize_money(applied * HUNDRED / gross)
        if gross > ZERO
        else quantize_money(asked if asked is not None else ZERO)
    )
    return LineDiscount(amount=applied, percent=rate, source=source)


@dataclass(frozen=True, slots=True)
class LinePrice:
    """The price a line starts at, and where it came from."""

    price: Decimal
    #: PRICE_LIST, BATCH_PTR, BATCH_PTS, PRICE_LEVEL or PRODUCT on a sale; on
    #: a purchase also RATE_CONTRACT, CATALOGUE, PRICE_REVISION or TYPED.
    source: str


def batch_trade_rate(
    *,
    trade_class: str | None,
    ptr: Decimal | None,
    pts: Decimal | None,
) -> LinePrice | None:
    """Return the batch rate a buyer of this trade class takes (PG-14).

    A RETAILER takes the batch's price to retailer, a STOCKIST its price to
    stockist; anyone else -- OTHER, or a customer nobody classed -- takes
    neither, and so does a batch with no rate for the class. None is "no
    batch rate", and the line falls through to the rest of the ranking.
    """
    if trade_class == "RETAILER" and ptr is not None:
        return LinePrice(price=ptr, source="BATCH_PTR")
    if trade_class == "STOCKIST" and pts is not None:
        return LinePrice(price=pts, source="BATCH_PTS")
    return None


def resolve_unit_price(
    *,
    product_price: Decimal | None,
    level_rate: Decimal | None = None,
    list_rate: Decimal | None = None,
    batch_rate: LinePrice | None = None,
) -> LinePrice:
    """Return the price a line starts at when none is typed (SEL-9, PG-14).

    Most specific arrangement first, as the discount ranking above: a fixed
    price a list agreed for this customer, then the trade rate of the batch
    the line sells from (``batch_trade_rate``), then the customer's price
    level, then the product's own selling price. A typed price beats all
    four, which is why a caller asks only when the line names none.

    The batch rate sits below the list because a list is a price agreed with
    this customer, and an agreement beats a rate printed for a whole trade
    class; it sits above the level because it is the same kind of tier rate
    made specific to the goods actually leaving -- the reason a pharma
    distributor keeps PTR per batch at all.
    """
    if list_rate is not None:
        return LinePrice(price=list_rate, source="PRICE_LIST")
    if batch_rate is not None:
        return batch_rate
    if level_rate is not None:
        return LinePrice(price=level_rate, source="PRICE_LEVEL")
    return LinePrice(price=product_price or ZERO, source="PRODUCT")


def resolve_supplier_unit_price(
    *,
    typed: Decimal | None,
    contract_rate: Decimal | None = None,
    list_rate: Decimal | None = None,
    catalogue_rate: Decimal | None = None,
    fallback: Callable[[], LinePrice],
) -> LinePrice:
    """Return the price a purchase line is bought at, and where it came from.

    The supplier side of the ranking (BUY-3, BUY-4, PG-9), most specific
    first: a rate contract in force with this supplier on the order's date,
    then the supplier's price list's fixed rate at the line's quantity, then
    the supplier's catalogue price, then ``fallback`` -- a dated price
    revision or the product's purchase price, which the caller reads only
    when nothing above answered.

    A typed price beats all of them, as on a sale. A typed price equal to the
    one the ranking gives is that price echoed back -- a client re-saving a
    line it was shown -- so it keeps the source it came from; otherwise it is
    ``TYPED``. That is what keeps an order on its rate contract across edits.
    """
    for price, source in (
        (contract_rate, "RATE_CONTRACT"),
        (list_rate, "PRICE_LIST"),
        (catalogue_rate, "CATALOGUE"),
    ):
        if price is not None:
            if typed is None or typed == price:
                return LinePrice(price=price, source=source)
            return LinePrice(price=typed, source="TYPED")
    resolved = fallback()
    if typed is None or typed == resolved.price:
        return resolved
    return LinePrice(price=typed, source="TYPED")


@dataclass(frozen=True, slots=True)
class SchemeFree:
    """What a supplier's free scheme gives one purchase line (PG-11)."""

    #: The free quantity the line carries: the scheme's when the line left it
    #: blank and the scheme gives its own product, else what was typed.
    free_quantity: Decimal
    #: Whether the line's free quantity came from the scheme (filled, or a
    #: typed figure equal to it -- the scheme echoed back on a re-save).
    applied: bool
    #: Free goods of *another* product the scheme earns, for a line of their
    #: own; zero when the scheme gives the same product or earns nothing.
    other_product_quantity: Decimal
    #: Free goods of the line's **own** product, in stock units, that are not
    #: a whole number of the line's unit -- 2 pieces earned by 2 BOX of 12 --
    #: for a free line of their own in the stock unit. Zero otherwise.
    own_stock_quantity: Decimal = ZERO


def resolve_supplier_free_goods(
    *,
    typed: Decimal | None,
    quantity: Decimal,
    buy_quantity: Decimal | None = None,
    scheme_free_quantity: Decimal | None = None,
    same_product: bool = True,
    stock_factor: Decimal = Decimal("1"),
) -> SchemeFree:
    """Return the free goods a purchase line takes from a supplier's scheme.

    A scheme "buy 10, get 2" earns ``floor(bought / 10) * 2`` free, and both
    figures are **stock units** (D-PRC-39): a scheme names a product, a
    product has one stock unit, and a line bought by the box is counted at
    the pieces it stands for -- ``quantity`` times ``stock_factor``, the
    stock units one of the line's units holds. 2 BOX of 12 are 24 bought and
    earn 4.

    Of the same product the free goods fill the line's free quantity, in the
    line's unit, where they are a whole number of it -- but only where the
    line left it blank: ``None`` takes the scheme and an explicit ``0``
    refuses it, the same two answers as a discount. Where they are not a
    whole number of the line's unit they fill nothing on this line and are
    answered as ``own_stock_quantity``, for a free line of the same product
    in its stock unit. Of another product they fill nothing on this line
    either; the caller offers that as a line of its own (paid 0, free n). No
    scheme, or too few bought to earn anything, leaves the line as typed
    (blank is zero).
    """
    earned = ZERO
    if (
        buy_quantity is not None
        and scheme_free_quantity is not None
        and buy_quantity > ZERO
        and quantity > ZERO
    ):
        bought = quantize_money(quantity * stock_factor)
        earned = (bought // buy_quantity) * scheme_free_quantity
    if same_product and earned > ZERO and stock_factor != Decimal("1"):
        in_line = quantize_money(earned / stock_factor)
        if in_line <= ZERO or in_line != in_line.to_integral_value():
            return SchemeFree(
                free_quantity=typed if typed is not None else ZERO,
                applied=False,
                other_product_quantity=ZERO,
                own_stock_quantity=earned,
            )
        earned = in_line
    if not same_product:
        return SchemeFree(
            free_quantity=typed if typed is not None else ZERO,
            applied=False,
            other_product_quantity=earned,
        )
    if earned <= ZERO:
        return SchemeFree(
            free_quantity=typed if typed is not None else ZERO,
            applied=False,
            other_product_quantity=ZERO,
        )
    if typed is None or typed == earned:
        return SchemeFree(
            free_quantity=earned, applied=True, other_product_quantity=ZERO
        )
    return SchemeFree(free_quantity=typed, applied=False, other_product_quantity=ZERO)


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
    did on a purchase order until D-BUY-19 split it here too.

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


def inherited_share(amount: Decimal, *, part: Decimal, whole: Decimal) -> Decimal:
    """Return the part of a source line's discount share a later line inherits.

    A downstream document inherits an *amount* pro-rated by the share of the
    source line it covers -- a receipt of 4 of an ordered 10 takes four tenths
    of the order line's share of the whole-order discount -- where a *rate*
    would be inherited as itself. Capped at the whole: covering more than the
    source line never inherits more than the source line was given.

    Args:
        amount: The source line's share.
        part: The quantity this line covers.
        whole: The source line's quantity the share was computed on.

    Returns:
        The inherited share, quantised to money; zero when there is nothing to
        inherit or nothing to pro-rate against.

    """
    if amount <= ZERO or part <= ZERO or whole <= ZERO:
        return ZERO
    if part >= whole:
        return quantize_money(amount)
    return quantize_money(amount * part / whole)


def continued_share(
    amount: Decimal, *, before: Decimal, part: Decimal, whole: Decimal
) -> Decimal:
    """Return the slice of a source line's amount one continuing line takes.

    A delivery note continues an order line and a bill continues a note line,
    usually in parts. The source line's share of a discount on the whole
    order is theirs between them, so each part takes the slice between where
    the earlier parts stopped and where it stops -- the amount up to
    ``before + part`` less the amount up to ``before``, each rounded once.
    The slices therefore sum to the source line's figure exactly, the part
    that completes the line taking whatever the rounding left, where
    pro-rating each part alone leaves a residual that belongs to nobody
    (D-PRC-1).

    Args:
        amount: The source line's figure.
        before: The quantity of the source line already continued elsewhere.
        part: The quantity this line continues.
        whole: The source line's quantity the figure was computed on.

    Returns:
        This line's slice; zero where there is nothing to continue.

    """
    if amount <= ZERO or part <= ZERO or whole <= ZERO:
        return ZERO
    start = min(max(before, ZERO), whole)
    stop = min(start + part, whole)
    return quantize_money(
        quantize_money(amount * stop / whole) - quantize_money(amount * start / whole)
    )


def continued_free_goods(
    offered: Decimal,
    *,
    before: Decimal,
    part: Decimal,
    whole: Decimal,
    already: Decimal,
) -> Decimal:
    """Return the free goods a continuing line takes when it says nothing.

    The source line's free goods in proportion to the quantity continued, in
    **whole units**: nobody can hand over 0.923 of a gift. What the share so
    far has earned, less what already went, goes now; the part that completes
    the line takes all that is left, so nothing is rounded away and nothing
    goes twice (D-PRC-4). A source line that charges for nothing -- a gift
    line -- gives what is left of it whole.

    Args:
        offered: The source line's free quantity.
        before: The charged quantity of the source line already continued.
        part: The charged quantity this line continues.
        whole: The source line's charged quantity.
        already: The free goods the earlier lines already took.

    Returns:
        The free quantity this line takes.

    """
    left = offered - already
    if offered <= ZERO or left <= ZERO:
        return ZERO
    if whole <= ZERO or before + part >= whole:
        return left
    if part <= ZERO:
        return ZERO
    earned = (offered * (before + part) / whole) // 1
    return min(max(earned - already, ZERO), left)
