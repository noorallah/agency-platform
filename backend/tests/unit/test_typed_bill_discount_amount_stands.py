"""A bill discount typed as an amount stays that amount.

D-PRC-35: a draft bill of a note for 10 at 84.00 with 25.00 typed off the
whole bill read 961.70. Saved again with the discount left out it read
``bill_discount_amount`` 25.0001 and 961.6999: the bill kept both figures and
not which was typed, carried the four-place rate (2.9762%) and worked it
again.

A bill now records how its discount was stated. An amount is carried as the
amount -- and stands when the lines change value, the rate beside it moving
-- and a rate is carried as the rate. Every case runs on a request-shaped
session.
"""

from decimal import Decimal

from tests.unit.test_order_bill_discount_reaches_the_bill import _Trade

D = Decimal


def test_a_typed_amount_comes_back_as_itself_from_an_edit_that_omits_it() -> None:
    """The check's own steps: 25.00, then a re-save that does not mention it."""
    trade = _Trade()
    note = trade.note(trade.order("10"), "10")
    draft = trade.bill(note, "10", approve=False, bill_discount_amount="25")
    assert (draft.bill_discount_amount, draft.grand_total) == (
        D("25.0000"),
        D("961.7000"),
    )
    rate = draft.bill_discount_percent

    again = trade.resave(draft, "10")

    assert (again.bill_discount_amount, again.grand_total) == (
        D("25.0000"),
        D("961.7000"),
    )
    assert again.bill_discount_percent == rate == D("2.9762")
    assert (again.bill_discount_source, again.bill_discount_typed_as) == (
        "typed",
        "amount",
    )
    # And a third time: nothing drifts however often it is saved.
    third = trade.resave(again, "10")
    assert third.bill_discount_amount == D("25.0000")


def test_a_typed_amount_stands_when_the_lines_change_value() -> None:
    """Half the quantity: still 25.00 off, and the rate beside it doubles."""
    trade = _Trade()
    note = trade.note(trade.order("10"), "10")
    draft = trade.bill(note, "10", approve=False, bill_discount_amount="25")

    smaller = trade.resave(draft, "5")

    assert smaller.bill_discount_amount == D("25.0000")
    assert smaller.bill_discount_percent == D("5.9524")
    # 5 x 84 less 25, plus 18%.
    assert smaller.grand_total == D("466.1000")
    assert smaller.bill_discount_typed_as == "amount"


def test_a_typed_rate_is_kept_as_the_rate() -> None:
    """10% typed: 84.00 on ten, 42.00 on five, and still 10%."""
    trade = _Trade()
    note = trade.note(trade.order("10"), "10")
    draft = trade.bill(note, "10", approve=False, bill_discount_percent="10")
    assert (draft.bill_discount_amount, draft.bill_discount_typed_as) == (
        D("84.0000"),
        "percent",
    )

    smaller = trade.resave(draft, "5")

    assert (smaller.bill_discount_percent, smaller.bill_discount_amount) == (
        D("10.0000"),
        D("42.0000"),
    )
    assert smaller.bill_discount_typed_as == "percent"


def test_a_bill_saved_before_the_bill_recorded_it_carries_the_rate() -> None:
    """Nothing says which was typed: the rate, as every bill did before."""
    trade = _Trade()
    note = trade.note(trade.order("10"), "10")
    draft = trade.bill(note, "10", approve=False, bill_discount_amount="84")
    draft.bill_discount_typed_as = None
    trade.session.commit()

    smaller = trade.resave(draft, "5")

    assert (smaller.bill_discount_percent, smaller.bill_discount_amount) == (
        D("10.0000"),
        D("42.0000"),
    )


def test_a_figure_named_on_the_edit_replaces_how_it_was_typed() -> None:
    """An amount, then an edit that names a rate: the rate is what is kept."""
    trade = _Trade()
    note = trade.note(trade.order("10"), "10")
    draft = trade.bill(note, "10", approve=False, bill_discount_amount="25")

    rated = trade.resave(draft, "10", bill_discount_percent="10")
    smaller = trade.resave(rated, "5")

    assert rated.bill_discount_typed_as == "percent"
    assert (smaller.bill_discount_percent, smaller.bill_discount_amount) == (
        D("10.0000"),
        D("42.0000"),
    )


def test_a_counter_bills_typed_amount_stands_across_edits() -> None:
    """Typed on a bill that raises its own order: 25.00 again, and on twenty."""
    trade = _Trade(counter=True)
    draft = trade.counter_bill("10", bill_discount_amount="25")
    assert (draft.bill_discount_amount, draft.grand_total) == (
        D("25.0000"),
        D("961.7000"),
    )

    same = trade.resave(draft, "10")
    assert (same.bill_discount_amount, same.grand_total) == (
        D("25.0000"),
        D("961.7000"),
    )
    grown = trade.resave(same, "20")

    # 20 x 84 less the same 25.00, plus 18%.
    assert (grown.bill_discount_amount, grown.grand_total) == (
        D("25.0000"),
        D("1952.9000"),
    )
    assert grown.bill_discount_typed_as == "amount"
    assert trade.own_order(grown).bill_discount_amount == D("25.0000")


def test_an_inherited_discount_records_no_typing() -> None:
    """The order's discount reaching the bill was typed on nobody's bill."""
    trade = _Trade()
    note = trade.note(trade.order("10", bill_discount_amount="25"), "10")

    bill = trade.bill(note, "10", approve=False)

    assert (bill.bill_discount_source, bill.bill_discount_typed_as) == (
        "inherited",
        None,
    )
    assert trade.resave(bill, "5").bill_discount_amount == D("12.5000")
