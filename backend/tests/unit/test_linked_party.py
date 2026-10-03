"""A customer that is also a supplier, and their combined statement (ACC-11).

A shop the firm sells to and buys from is linked once, on the customer. Only
one customer may claim a supplier, two businesses with different PANs cannot
be linked, and the combined statement nets what the shop owes against what the
firm owes it, line by line in date order.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal

import pytest

from app.core.exceptions import ResourceNotFoundError, ValidationError
from app.customers.models import Customer
from app.customers.schemas.customer import CustomerType, CustomerUpdate
from app.customers.schemas.statement import CustomerStatement, CustomerStatementLine
from app.customers.services import CustomerService, combined_statement
from app.customers.services.combined_statement import CombinedStatementService
from app.vendors.models import Vendor
from app.vendors.schemas.statement import SupplierStatement, SupplierStatementLine
from tests.unit.test_settlements import _Books, _session_factory

D = Decimal


def _link(books: _Books, customer: Customer, vendor: Vendor | None) -> Customer:
    return CustomerService(books.session).update(
        customer.id,
        CustomerUpdate(
            code=customer.code,
            customer_type=CustomerType(customer.customer_type),
            name=customer.name,
            currency_code="INR",
            linked_vendor_id=None if vendor is None else vendor.id,
        ),
        firm_scope=books.firm.id,
        actor_id=books.actor_id,
    )


def test_a_customer_links_its_supplier_record_once() -> None:
    books = _Books(_session_factory()())
    linked = _link(books, books.customer, books.vendor)
    assert linked.linked_vendor_id == books.vendor.id

    other = Customer(
        firm_id=books.firm.id,
        code="C2",
        customer_type="BUSINESS",
        name="Customer Two",
        display_name="Customer Two",
        currency_code="INR",
        status="ACTIVE",
    )
    books.session.add(other)
    books.session.commit()
    with pytest.raises(ValidationError, match="already linked to the customer"):
        _link(books, other, books.vendor)

    unlinked = _link(books, books.customer, None)
    assert unlinked.linked_vendor_id is None
    assert _link(books, other, books.vendor).linked_vendor_id == books.vendor.id


def test_two_businesses_with_different_pans_are_not_linked() -> None:
    books = _Books(_session_factory()())
    books.customer.pan_number = "AAAPA1234A"
    books.vendor.pan = "BBBPB5678B"
    books.session.commit()
    with pytest.raises(ValidationError, match="different businesses"):
        _link(books, books.customer, books.vendor)


def _customer_side(*_: object, **__: object) -> CustomerStatement:
    return CustomerStatement(
        customer_id=books_ref["customer"],
        customer_code="C1",
        customer_name="Customer One",
        from_date=date(2026, 4, 1),
        to_date=date(2026, 4, 30),
        opening_balance=D("1000.00"),
        closing_balance=D("6000.00"),
        unapplied_advance=D("0.00"),
        lines=[
            CustomerStatementLine(
                transaction_date=date(2026, 4, 10),
                transaction_type="INVOICE",
                reference_number="SI-1",
                debit=D("5000.00"),
                credit=D("0.00"),
                balance=D("6000.00"),
            )
        ],
    )


def _supplier_side(*_: object, **__: object) -> SupplierStatement:
    return SupplierStatement(
        vendor_id=books_ref["vendor"],
        vendor_code="V1",
        vendor_name="Vendor One",
        from_date=date(2026, 4, 1),
        to_date=date(2026, 4, 30),
        opening_balance=D("500.00"),
        closing_balance=D("2500.00"),
        total_debit=D("1000.00"),
        total_credit=D("3000.00"),
        lines=[
            SupplierStatementLine(
                transaction_date=date(2026, 4, 5),
                transaction_type="BILL",
                reference_number="PB-1",
                debit=D("0.00"),
                credit=D("3000.00"),
                balance=D("3500.00"),
            ),
            SupplierStatementLine(
                transaction_date=date(2026, 4, 10),
                transaction_type="PAYMENT",
                reference_number="PAY-1",
                debit=D("1000.00"),
                credit=D("0.00"),
                balance=D("2500.00"),
            ),
        ],
    )


books_ref: dict[str, object] = {}


def test_the_combined_statement_nets_both_accounts_in_date_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    books = _Books(_session_factory()())
    books_ref.update(customer=books.customer.id, vendor=books.vendor.id)
    service = CombinedStatementService(books.session)
    with pytest.raises(ValidationError, match="not linked to a supplier"):
        service.for_customer(
            books.customer.id,
            firm_scope=books.firm.id,
            from_date=date(2026, 4, 1),
            to_date=date(2026, 4, 30),
        )
    _link(books, books.customer, books.vendor)
    monkeypatch.setattr(
        combined_statement.CustomerStatementService, "statement", _customer_side
    )
    monkeypatch.setattr(
        combined_statement.SupplierStatementService, "statement", _supplier_side
    )
    found = service.for_customer(
        books.customer.id,
        firm_scope=books.firm.id,
        from_date=date(2026, 4, 1),
        to_date=date(2026, 4, 30),
    )
    assert found.net_opening == D("500.00"), "owes 1,000, is owed 500"
    assert [(line.account, line.reference_number) for line in found.lines] == [
        ("PAYABLE", "PB-1"),
        ("RECEIVABLE", "SI-1"),
        ("PAYABLE", "PAY-1"),
    ], "by date; on one day the customer account first"
    assert [line.net_balance for line in found.lines] == [
        D("-2500.00"),
        D("2500.00"),
        D("3500.00"),
    ]
    assert found.net_closing == D("3500.00"), "6,000 owed less 2,500 owing"

    with pytest.raises(ResourceNotFoundError):
        service.for_customer(
            books.vendor.id,
            firm_scope=books.firm.id,
            from_date=date(2026, 4, 1),
            to_date=date(2026, 4, 30),
        )
