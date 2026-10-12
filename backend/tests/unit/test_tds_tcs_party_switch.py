"""Backlog 113 (S8): a TDS switch on each supplier, a TCS switch on each customer.

Both are on for every party already stored, so nothing changes until somebody
switches one off. Off means the server proposes and charges nothing for that
party: no 194C/194J deduction on a bill or a payment, nothing asked under
194Q, no TCS on a receipt. A deduction typed on one document still stands on
that document and on no other.
"""

# ruff: noqa: D103

from decimal import Decimal

import pytest

from app.core.exceptions import ValidationError
from app.customers.schemas import CustomerUpdate
from app.finance.services.tds_194q import Tds194QService
from app.finance.services.tds_sections import TdsSectionService
from app.tcs.services import TcsService
from app.vendors.schemas import VendorUpdate
from tests.unit import test_tcs as tcs
from tests.unit import test_tds_194q as q194
from tests.unit.test_cash_purchase import _books
from tests.unit.test_settlements import WHEN
from tests.unit.test_tds_194c_194j import _approve, _bill, _draft, _pay, _supplier

pytestmark = pytest.mark.typed_document_numbers


def test_a_supplier_switched_off_is_deducted_nothing_on_a_bill() -> None:
    books = _books()
    vendor = _supplier(books, "194C")
    vendor.tds_applicable = False
    books.session.commit()

    bill = _bill(books, "40000.00", tax="7200.00")

    assert (bill.tds_amount, bill.tds_section) == (Decimal("0"), None)
    assert bill.tds_proposed_amount == Decimal("0")
    proposal = TdsSectionService(books.session).propose(
        vendor, firm_id=books.firm.id, on=WHEN, bill_amount=Decimal("40000")
    )
    assert proposal.switched_off is True
    assert (proposal.due, proposal.proposed, proposal.applies) == (
        Decimal("0"),
        Decimal("0"),
        False,
    )
    # The section is still named: it is what an override is filed under.
    assert proposal.section == "194C"


def test_switching_back_on_proposes_the_year_again() -> None:
    books = _books()
    vendor = _supplier(books, "194C")
    vendor.tds_applicable = False
    books.session.commit()
    _bill(books, "40000.00")

    vendor.tds_applicable = True
    books.session.commit()
    bill = _bill(books, "50000.00")

    # 2% on both bills past the single limit: the year is what is owed on.
    assert bill.tds_amount == Decimal("1800.00")


def test_an_override_on_one_bill_changes_that_bill_only() -> None:
    books = _books()
    vendor = _supplier(books, "194C")
    vendor.tds_applicable = False
    books.session.commit()

    overridden = _approve(books, _draft(books, "40000.00"), tds=Decimal("800"))
    following = _bill(books, "40000.00")

    assert (overridden.tds_amount, overridden.tds_section) == (
        Decimal("800.00"),
        "194C",
    )
    assert overridden.tds_proposed_amount == Decimal("0")
    assert (following.tds_amount, following.tds_section) == (Decimal("0"), None)


def test_an_override_still_stays_below_the_bill_when_switched_off() -> None:
    books = _books()
    vendor = _supplier(books, "194C")
    vendor.tds_applicable = False
    books.session.commit()

    with pytest.raises(ValidationError, match="less than"):
        _approve(books, _draft(books, "400.00"), tds=Decimal("400"))


def test_a_payment_to_a_supplier_switched_off_proposes_nothing() -> None:
    books = _books()
    vendor = _supplier(books, "194C")
    vendor.tds_applicable = False
    books.session.commit()

    advance = _pay(books, "50000.00")
    typed = _pay(books, "50000.00", tds="1000.00")

    assert advance.tds_proposed_amount == Decimal("0")
    assert advance.tds_amount == Decimal("0")
    # What somebody types on one payment is deducted on that payment.
    assert (typed.tds_amount, typed.tds_section) == (Decimal("1000.00"), "194C")


def test_194q_asks_a_supplier_switched_off_for_nothing() -> None:
    books = q194._Books(q194._session_factory()())
    books.vendor.pan = "AAACV1234A"
    books.session.commit()
    q194._switch_on(books)
    q194._bill(books, "PI-1", "6000000")
    service = Tds194QService(books.session)
    on = service.supplier(books.vendor.id, firm_id=books.firm.id, on=WHEN)
    assert (on.due, on.applies) == (Decimal("1000.00"), True)

    books.vendor.tds_applicable = False
    books.session.commit()
    off = service.supplier(books.vendor.id, firm_id=books.firm.id, on=WHEN)

    assert off.purchases == Decimal("6000000.00"), "what was bought still shows"
    assert (off.due, off.to_deduct, off.applies) == (
        Decimal("0"),
        Decimal("0"),
        False,
    )


def test_a_customer_switched_off_is_never_charged_tcs() -> None:
    books = tcs._Books(tcs._session_factory()())
    books.customer.tcs_applicable = False
    books.session.commit()

    books.receipt("4800000")
    past_the_line = books.receipt("400000")
    another = books.receipt("6000000", customer=books.anonymous)

    assert books.collection(past_the_line) is None
    assert books.collection(another) is not None, "the switch is per customer"
    preview = TcsService(books.session).preview(
        firm_id=books.firm.id,
        customer_id=books.customer.id,
        amount=Decimal("100000"),
        on=tcs.WHEN,
    )
    assert preview.applicable is False
    assert "switched off for this customer" in preview.reason
    assert preview.tcs_amount == Decimal("0")


def test_a_customer_switched_off_is_not_reported_short() -> None:
    books = tcs._Books(tcs._session_factory()())
    books.customer.tcs_applicable = False
    books.session.commit()
    books.receipt("6000000")

    rows = TcsService(books.session).charged_versus_due(
        firm_id=books.firm.id, on=tcs.WHEN
    )

    mine = [row for row in rows if row.customer_id == books.customer.id]
    assert [(row.tcs_due, row.position) for row in mine] == [(Decimal("0"), "SQUARE")]


def test_switching_a_customer_back_on_charges_the_next_receipt() -> None:
    books = tcs._Books(tcs._session_factory()())
    books.customer.tcs_applicable = False
    books.session.commit()
    books.receipt("5200000")

    books.customer.tcs_applicable = True
    books.session.commit()
    row = books.collection(books.receipt("100000"))

    # The year is a running total: 53 lakh received, 3 lakh past the line.
    assert row is not None and row.taxable_amount == Decimal("300000.00")


def test_both_switches_are_on_unless_said_and_an_edit_leaves_them_alone() -> None:
    supplier = VendorUpdate.model_validate({"code": "V001", "name": "Supplier"})
    assert supplier.tds_applicable is True
    assert "tds_applicable" not in supplier.model_dump(exclude_unset=True)
    customer = CustomerUpdate.model_validate(
        {
            "code": "C001",
            "name": "Customer",
            "customer_type": "BUSINESS",
            "currency_code": "INR",
        }
    )
    assert customer.tcs_applicable is True
    assert "tcs_applicable" not in customer.model_dump(exclude_unset=True)
