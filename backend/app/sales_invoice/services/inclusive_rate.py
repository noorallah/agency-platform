"""Read a rate typed with GST in it back to the rate before tax (backlog 64 row 4).

A counter types the shelf price, which includes GST; every document, posting,
return and filing in this platform reads a line's ``unit_price`` as the rate
before tax. Rather than teach all of them a second meaning, a bill whose
``rate_includes_tax`` is on has each typed rate turned into its pre-tax
equivalent before the line is written, and keeps the figure as typed in
``entered_rate`` for the print and the editor.

The rate used is what the buyer is **billed**: the components not already
inside the price and not reverse-charged -- exactly what the tax engine adds
to the line. A rule that depends on the value (a slab) is asked at the gross
value first and again at the taxable value derived from it; if the second
answer differs it is taken, once, and the derivation stops there.

Rounding. The taxable value is kept at the documents' four-decimal scale
rather than rounded to the paisa first. Rounding it to two places and then
charging tax on that leaves taxable plus tax a paisa away from the typed
total in roughly one case in seven (100 at 18% is 84.75 + 15.26 = 100.01);
at four places the two halves round to the paisa together (84.7458 +
15.2542), and the residual is at most a hundredth of a paisa per unit, which
nothing on the bill shows. Where a quantity is large enough for that to reach
a paisa, the tax engine's figure stands and the difference is the round-off's
to absorb -- the tax is never adjusted to make the total come out.
"""

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from app.core.utils.money import quantize_money
from app.tax.schemas import TaxRuleSimulationResponse

ZERO = Decimal("0")
HUNDRED = Decimal("100")


@dataclass(frozen=True, slots=True)
class PreTaxLine:
    """One typed line, read back to the rates the documents store."""

    #: The rate before tax: what ``unit_price`` stores.
    unit_price: Decimal
    #: The typed discount amount before tax, or None where none was typed.
    discount_amount: Decimal | None
    #: The rate as typed, GST included.
    entered_rate: Decimal
    #: The rate of tax billed on the line, as a fraction (0.18 for 18%).
    tax_rate: Decimal


def billed_rate(response: TaxRuleSimulationResponse) -> Decimal:
    """Return the fraction of the line's value the buyer is billed as tax.

    Tax already inside the price is not billed again, and reverse-charged tax
    is accounted for by the buyer, so neither is part of the rate a typed
    price has to be divided by.
    """
    if response.reverse_charge or response.exempt:
        return ZERO
    percent = sum(
        (
            component.percentage
            for component in response.applied_components
            if not component.included_in_price
        ),
        ZERO,
    )
    return Decimal(str(percent)) / HUNDRED


def derive_pre_tax(
    *,
    quantity: Decimal,
    entered_rate: Decimal,
    discount_percent: Decimal | None,
    discount_amount: Decimal | None,
    rate_at: Callable[[Decimal], Decimal],
) -> PreTaxLine:
    """Turn one typed inclusive rate into the pre-tax rate the line stores.

    Args:
        quantity: The quantity billed.
        entered_rate: The rate as typed, GST included.
        discount_percent: A typed percentage, which applies unchanged.
        discount_amount: A typed amount, which is gross like the rate and
            converts the same way. An amount beats a percentage.
        rate_at: The billed tax rate, as a fraction, for a line of the value
            given -- asked twice at most, for a slabbed rule.

    Returns:
        The pre-tax rate, the pre-tax discount amount where one was typed,
        and the rate of tax that decided them.

    """
    gross = quantize_money(quantity * entered_rate)
    if discount_amount is not None:
        net = gross - discount_amount
    elif discount_percent:
        net = gross * (HUNDRED - discount_percent) / HUNDRED
    else:
        net = gross
    net = max(quantize_money(net), ZERO)
    rate = rate_at(net)
    taxable = quantize_money(net / (1 + rate))
    if taxable > ZERO:
        # A slab is decided by the value taxed, which is only known now.
        second = rate_at(taxable)
        if second != rate:
            rate = second
            taxable = quantize_money(net / (1 + rate))
    unit_price = quantize_money(entered_rate / (1 + rate))
    pre_tax_discount: Decimal | None = None
    if discount_amount is not None:
        # Whatever the line's own gross leaves above the taxable value is the
        # discount, so the line taxes exactly what the typed total implies.
        pre_tax_discount = (
            max(quantize_money(quantity * unit_price) - taxable, ZERO)
            if discount_amount > ZERO
            else ZERO
        )
    return PreTaxLine(
        unit_price=unit_price,
        discount_amount=pre_tax_discount,
        entered_rate=entered_rate,
        tax_rate=rate,
    )
