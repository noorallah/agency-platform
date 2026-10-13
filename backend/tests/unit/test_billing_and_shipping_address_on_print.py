"""Which of a customer's addresses a document prints (D-SELL-92, 93, 94).

Found by trying decision D6 on a running firm: a customer with two billing
addresses was billed at whichever the database returned first, a customer with
no shipping address had an empty SHIPPED TO block, and an order's print
repeated the billing address whatever address the order named.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.customers.models import Customer, CustomerAddress
from app.customers.services.ship_to import billing_address, shipping_address
from app.document_framework.services.print_support import customer_party
from app.tax.services.place_of_supply import SupplyPlaceResolver
from tests.unit.test_gst_returns import _Books, _session_factory

_START = datetime(2026, 4, 1, tzinfo=UTC)


def _address(
    books: _Books,
    customer: Customer,
    kind: str,
    city: str,
    *,
    age: int,
    state: str = "Karnataka",
    billing: bool = False,
    shipping: bool = False,
) -> CustomerAddress:
    """Give the customer one address; a larger ``age`` was added later."""
    row = CustomerAddress(
        customer_id=customer.id,
        address_type=kind,
        address_line1=f"1 {city} Road",
        city=city,
        state=state,
        country="IN",
        postal_code="560001",
        is_default_billing=billing,
        is_default_shipping=shipping,
        created_at=_START + timedelta(days=age),
    )
    books.session.add(row)
    books.session.commit()
    return row


def _lines(books: _Books, kind: str, address: CustomerAddress | None = None) -> str:
    """Return the address a document prints for the walk-in buyer, as one string."""
    block = customer_party(
        books.session,
        books.walk_in.id,
        kind,
        address_id=address.id if address is not None else None,
    )
    assert block is not None
    return " | ".join(block.address_lines)


def test_the_default_billing_address_outranks_an_older_billing_one() -> None:
    """Two billing addresses: the one marked default is the one printed."""
    books = _Books(_session_factory()())
    _address(books, books.walk_in, "BILLING", "Oldtown", age=0)
    _address(books, books.walk_in, "BILLING", "Headtown", age=1, billing=True)

    printed = _lines(books, "BILLING")

    assert "Headtown" in printed
    assert "Oldtown" not in printed


def test_an_address_of_another_kind_marked_default_billing_is_billed() -> None:
    """One office address marked default for billing prints as BILLED TO."""
    books = _Books(_session_factory()())
    _address(books, books.walk_in, "OFFICE", "Soletown", age=0, billing=True)

    assert "Soletown" in _lines(books, "BILLING")


def test_a_customer_with_one_address_of_any_kind_is_billed_there() -> None:
    """No billing address and no default: the only address there is."""
    books = _Books(_session_factory()())
    _address(books, books.walk_in, "HOME", "Hometown", age=0)

    assert "Hometown" in _lines(books, "BILLING")


def test_with_no_shipping_address_the_goods_go_to_the_billing_address() -> None:
    """SHIPPED TO is never a name with nothing under it."""
    books = _Books(_session_factory()())
    _address(books, books.walk_in, "BILLING", "Billtown", age=0, billing=True)

    assert "Billtown" in _lines(books, "SHIPPING")


def test_the_default_shipping_address_outranks_an_older_shipping_one() -> None:
    """A document naming no address prints the default shipping address."""
    books = _Books(_session_factory()())
    _address(books, books.walk_in, "BILLING", "Billtown", age=0, billing=True)
    _address(books, books.walk_in, "SHIPPING", "Firstgodown", age=1)
    _address(books, books.walk_in, "SHIPPING", "Maingodown", age=2, shipping=True)

    printed = _lines(books, "SHIPPING")

    assert "Maingodown" in printed
    assert "Firstgodown" not in printed


def test_the_address_a_document_names_is_printed_even_after_it_is_deleted() -> None:
    """Where the goods went stays on the paper."""
    books = _Books(_session_factory()())
    _address(books, books.walk_in, "SHIPPING", "Maingodown", age=0, shipping=True)
    named = _address(books, books.walk_in, "SHIPPING", "Sitegodown", age=1)
    named.is_deleted = True
    books.session.commit()

    assert "Sitegodown" in _lines(books, "SHIPPING", named)


def test_the_two_choices_are_made_in_the_order_given() -> None:
    """The helpers are pure: first default, then first of the kind."""
    billing = CustomerAddress(address_type="BILLING", is_default_billing=False)
    office = CustomerAddress(address_type="OFFICE", is_default_billing=True)
    godown = CustomerAddress(address_type="SHIPPING", is_default_shipping=False)

    assert billing_address([billing, office, godown]) is office
    assert billing_address([godown, billing]) is billing
    assert billing_address([godown]) is godown
    assert billing_address([]) is None
    assert shipping_address([billing, godown]) is godown
    assert shipping_address([billing, office]) is None


def test_the_place_of_supply_reads_the_address_the_bill_prints() -> None:
    """An unregistered buyer's default billing address decides the state."""
    books = _Books(_session_factory()())
    _address(books, books.walk_in, "BILLING", "Oldtown", age=0, state="Karnataka")
    _address(
        books,
        books.walk_in,
        "BILLING",
        "Chennai",
        age=1,
        state="Tamil Nadu",
        billing=True,
    )
    books.session.expire_all()

    resolver = SupplyPlaceResolver(books.session)

    assert resolver.buyer_state(books.walk_in.id) == "33"
    assert "Chennai" in _lines(books, "BILLING")
