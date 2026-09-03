"""The one discount rule, and the questions it has to answer the same way.

Nine services used to answer these for themselves, and they disagreed: four of
them read the amount alone and stored the percentage without applying it. The
table below is what "the same way" means.
"""

from decimal import Decimal

import pytest

from app.core.exceptions import ValidationError
from app.core.utils.pricing import (
    apportion,
    resolve_bill_discount,
    resolve_line_discount,
)

THOUSAND = Decimal("1000")


def test_an_explicit_amount_beats_an_explicit_percentage() -> None:
    """What somebody typed in currency is what they meant."""
    result = resolve_line_discount(
        gross=THOUSAND, percent=Decimal("10"), amount=Decimal("50")
    )
    assert result.amount == Decimal("50.00")
    assert result.source == "amount"


def test_the_recorded_rate_is_derived_from_the_amount_applied() -> None:
    """The pair on the line has to agree with itself.

    A line saying 10% and 50.00 against 1,000.00 is one nobody can reconcile,
    and it is what echoing back the caller's percentage produced.
    """
    result = resolve_line_discount(
        gross=THOUSAND, percent=Decimal("10"), amount=Decimal("50")
    )
    assert result.percent == Decimal("5.00")


def test_a_percentage_is_applied_rather_than_merely_stored() -> None:
    """The defect this whole rule exists to close."""
    result = resolve_line_discount(gross=THOUSAND, percent=Decimal("10"))
    assert result.amount == Decimal("100.00")
    assert result.source == "percent"


def test_the_customer_default_fills_in_only_where_nothing_was_said() -> None:
    """Silence takes the standing arrangement."""
    result = resolve_line_discount(gross=THOUSAND, customer_default=Decimal("10"))
    assert result.amount == Decimal("100.00")
    assert result.source == "customer"


def test_an_explicit_zero_beats_the_customer_default() -> None:
    """Saying "not this time" has to be expressible.

    None and zero are different answers, which is why the write schemas take
    `Decimal | None` rather than defaulting to zero.
    """
    result = resolve_line_discount(
        gross=THOUSAND, percent=Decimal("0"), customer_default=Decimal("10")
    )
    assert result.amount == Decimal("0.00")
    assert result.source == "percent"


def test_a_zero_amount_also_beats_the_customer_default() -> None:
    """Same reasoning, said in currency."""
    result = resolve_line_discount(
        gross=THOUSAND, amount=Decimal("0"), customer_default=Decimal("10")
    )
    assert result.amount == Decimal("0.00")


def test_nothing_said_and_nothing_standing_is_no_discount() -> None:
    """And it records no rate, rather than a rate of nothing applied."""
    result = resolve_line_discount(gross=THOUSAND)
    assert result.amount == Decimal("0")
    assert result.percent == Decimal("0")
    assert result.source == "none"


def test_a_discount_larger_than_the_line_is_refused() -> None:
    """Only goods_receipt refused this; the rest produced negative tax bases.

    The tax helpers read a negative base as zero tax while the negative itself
    flowed on into the document total.
    """
    with pytest.raises(ValidationError, match="cannot exceed"):
        resolve_line_discount(gross=THOUSAND, amount=Decimal("1500"))


def test_a_negative_discount_is_refused() -> None:
    """A discount that adds to the bill is a price rise by another name."""
    with pytest.raises(ValidationError, match="cannot be negative"):
        resolve_line_discount(gross=THOUSAND, amount=Decimal("-10"))


def test_a_hundred_percent_is_allowed_and_is_the_ceiling() -> None:
    """Giving one line away free is a real thing; giving away more is not."""
    result = resolve_line_discount(gross=THOUSAND, percent=Decimal("100"))
    assert result.amount == Decimal("1000.00")


def test_a_zero_value_line_records_the_rate_it_was_given() -> None:
    """There is no rate to derive from nothing, so the asked-for one stands."""
    result = resolve_line_discount(gross=Decimal("0"), percent=Decimal("10"))
    assert result.amount == Decimal("0.00")
    assert result.percent == Decimal("10.00")


def test_a_bill_discount_splits_in_proportion_to_the_lines() -> None:
    """Each line carries its share, because tax is charged per line."""
    shares = apportion(Decimal("100"), [Decimal("600"), Decimal("400")])
    assert shares == [Decimal("60.00"), Decimal("40.00")]


def test_the_shares_sum_exactly_to_the_figure_they_split() -> None:
    """Three equal lines and a hundred rupees does not divide evenly.

    Quantising each share on its own leaves a paisa belonging to nobody, and a
    document whose lines do not sum to its own total is one no reconciliation
    can accept.
    """
    weights = [Decimal("100"), Decimal("100"), Decimal("100")]
    shares = apportion(Decimal("100"), weights)
    assert sum(shares, Decimal("0")) == Decimal("100.00")


def test_the_rounding_residual_goes_to_the_largest_line() -> None:
    """Where it is the smallest proportional distortion."""
    shares = apportion(Decimal("10"), [Decimal("1"), Decimal("1"), Decimal("1")])
    assert sum(shares, Decimal("0")) == Decimal("10.00")
    # Three equal weights, so the first is as large as any and takes it.
    assert shares[0] > shares[1]


def test_a_line_worth_nothing_is_discounted_by_nothing() -> None:
    """A free line has no value for a discount to come off."""
    shares = apportion(Decimal("100"), [Decimal("1000"), Decimal("0")])
    assert shares == [Decimal("100.00"), Decimal("0")]


def test_a_document_worth_nothing_still_places_the_whole_figure() -> None:
    """Nothing to weigh against, so it lands somewhere rather than vanishing."""
    shares = apportion(Decimal("50"), [Decimal("0"), Decimal("0")])
    assert sum(shares, Decimal("0")) == Decimal("50.00")


def test_no_lines_means_no_shares() -> None:
    """And not an error: an empty document is refused elsewhere."""
    assert apportion(Decimal("100"), []) == []


def test_nothing_to_split_gives_every_line_nothing() -> None:
    """The ordinary case -- most documents carry no bill discount at all."""
    assert apportion(Decimal("0"), [Decimal("10"), Decimal("20")]) == [
        Decimal("0"),
        Decimal("0"),
    ]


def test_a_bill_discount_larger_than_the_document_is_refused() -> None:
    """The same refusal a line gets, and it names the document rather than a line.

    The two share one implementation, so the message has to be told which of
    them it is talking about; a bill discount refused for exceeding "the line
    amount" sends the reader looking at the wrong thing.
    """
    with pytest.raises(ValidationError, match="cannot exceed what the lines come to"):
        resolve_bill_discount(taxable=Decimal("1000"), amount=Decimal("1200"))


def test_a_bill_discount_comes_off_what_the_lines_already_discounted_to() -> None:
    """Never off the gross.

    Off the gross, two discounts are each computed as though the other had not
    happened, and the pair takes off more than either was agreed to.
    """
    result = resolve_bill_discount(taxable=Decimal("900"), percent=Decimal("10"))
    assert result.amount == Decimal("90.00")


def test_a_zero_value_line_records_an_explicit_refusal_as_zero() -> None:
    """Zero is an answer here exactly as it is everywhere else.

    The rate for a zero-value line used to be read off a chain of `or`s, which
    is falsy for an explicit zero -- so a line that had *refused* every
    arrangement recorded the customer's standing rate beside an amount of
    nothing. A promotion's gift line is the shape that makes it visible: a
    bill for nothing printing "7.5% discount".
    """
    result = resolve_line_discount(
        gross=Decimal("0"),
        percent=Decimal("0"),
        customer_default=Decimal("7.5"),
    )
    assert result.amount == Decimal("0.00")
    assert result.percent == Decimal("0.00")
    assert result.source == "percent"
