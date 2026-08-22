"""The one discount rule, and the questions it has to answer the same way.

Nine services used to answer these for themselves, and they disagreed: four of
them read the amount alone and stored the percentage without applying it. The
table below is what "the same way" means.
"""

from decimal import Decimal

import pytest

from app.core.exceptions import ValidationError
from app.core.utils.pricing import resolve_line_discount

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
