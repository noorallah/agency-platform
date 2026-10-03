"""Duplicate check and merge of customers and suppliers (MST-3, decision A136).

"Kumar Stores" was typed twice, the second time as "KUMAR STORES PVT LTD"
with the same phone. The check names it, by name and by phone. Merging the
second into the first moves its bill, adds its balance, keeps the first's
value where both have one custom field, and leaves the second soft-deleted
pointing at the first. A locked year's documents refuse a merge.
"""

# ruff: noqa: D103

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.business.models.framework import AttributeDefinition
from app.common.party_merge import (
    PartyMergeService,
    PartyMergeWrite,
    name_key,
    phone_key,
)
from app.core.exceptions import ValidationError
from app.customers.models import Customer, CustomerAttributeValue
from app.finance.models import FinancialYear
from app.sales_invoice.models import SalesInvoice
from app.vendors.models import Vendor
from tests.unit.test_gst_returns import _Books, _session_factory


def _twin(books: _Books) -> Customer:
    books.registered.phone = "+919876543210"
    books.registered.current_outstanding = Decimal("500")
    twin = Customer(
        firm_id=books.firm.id,
        code="C9",
        customer_type="BUSINESS",
        name="KUMAR STORES PVT LTD",
        display_name="KUMAR STORES PVT LTD",
        currency_code="INR",
        status="ACTIVE",
        phone="09876543210",
        current_outstanding=Decimal("300"),
    )
    books.session.add(twin)
    books.session.commit()
    return twin


def _field(
    books: _Books, customer: Customer, definition: AttributeDefinition, text: str
) -> None:
    books.session.add(
        CustomerAttributeValue(
            firm_id=books.firm.id,
            customer_id=customer.id,
            attribute_definition_id=definition.id,
            value_text=text,
        )
    )
    books.session.commit()


def test_names_and_phones_are_compared_as_a_person_would() -> None:
    assert name_key("Kumar Stores") == name_key("KUMAR STORES PVT. LTD.")
    assert name_key("M/s Sri Balaji Traders") == name_key("Sri Balaji")
    assert phone_key("+91 98765-43210") == phone_key("09876543210")


def test_the_check_names_the_likely_duplicate() -> None:
    books = _Books(_session_factory()())
    twin = _twin(books)
    found = PartyMergeService(books.session).duplicates(
        "CUSTOMER", firm_id=books.firm.id, name="Kumar Stores", phone="9876543210"
    )
    reasons = {candidate.id: candidate.reasons for candidate in found}
    assert reasons[twin.id] == ["same phone", "same name"]
    assert reasons[books.registered.id] == ["same phone", "same name"]


def test_a_merge_moves_documents_and_balances_and_keeps_the_survivors_field() -> None:
    books = _Books(_session_factory()())
    twin = _twin(books)
    bill = books.invoice("SI-9", customer=twin)
    site = AttributeDefinition(
        firm_id=books.firm.id,
        code="SITE",
        name="Site",
        entity_type="CUSTOMER",
        data_type="TEXT",
    )
    books.session.add(site)
    books.session.commit()
    _field(books, books.registered, site, "Main road")
    _field(books, twin, site, "Old address")

    result = PartyMergeService(books.session).merge(
        "CUSTOMER",
        books.registered.id,
        PartyMergeWrite(duplicate_id=twin.id, reason="Same shop typed twice"),
        firm_id=books.firm.id,
        actor_id=uuid4(),
    )
    assert "sales_invoices.customer_id" in result.tables
    assert result.rows_kept_from_survivor >= 1
    assert books.session.get(SalesInvoice, bill.id).customer_id == books.registered.id
    survivor = books.session.get(Customer, books.registered.id)
    assert survivor.current_outstanding == Decimal("800")
    gone = books.session.get(Customer, twin.id)
    assert gone.is_deleted and gone.merged_into_id == books.registered.id
    values = books.session.scalars(
        select(CustomerAttributeValue.value_text).where(
            CustomerAttributeValue.customer_id == books.registered.id
        )
    ).all()
    assert list(values) == ["Main road"]


def test_a_locked_years_documents_refuse_a_merge() -> None:
    books = _Books(_session_factory()())
    twin = _twin(books)
    books.invoice("SI-9", customer=twin)
    books.session.add(
        FinancialYear(
            firm_id=books.firm.id,
            code="FY26",
            name="2026-27",
            starts_on=date(2026, 4, 1),
            ends_on=date(2027, 3, 31),
            is_locked=True,
        )
    )
    books.session.commit()
    with pytest.raises(ValidationError, match="locked financial year"):
        PartyMergeService(books.session).merge(
            "CUSTOMER",
            books.registered.id,
            PartyMergeWrite(duplicate_id=twin.id, reason="Twice"),
            firm_id=books.firm.id,
            actor_id=uuid4(),
        )


def test_suppliers_merge_the_same_way() -> None:
    books = _Books(_session_factory()())
    first, second = (
        Vendor(
            firm_id=books.firm.id,
            code=code,
            name="Anand Agencies",
            display_name="Anand Agencies",
            status="ACTIVE",
        )
        for code in ("V1", "V2")
    )
    books.session.add_all([first, second])
    books.session.commit()
    service = PartyMergeService(books.session)
    assert [
        c.id
        for c in service.duplicates(
            "VENDOR", firm_id=books.firm.id, name="ANAND", excluding=first.id
        )
    ] == [second.id]
    service.merge(
        "VENDOR",
        first.id,
        PartyMergeWrite(duplicate_id=second.id, reason="Twice"),
        firm_id=books.firm.id,
        actor_id=uuid4(),
    )
    assert books.session.get(Vendor, second.id).merged_into_id == first.id
    with pytest.raises(ValidationError, match="into itself"):
        service.merge(
            "VENDOR",
            first.id,
            PartyMergeWrite(duplicate_id=first.id, reason="x"),
            firm_id=books.firm.id,
            actor_id=uuid4(),
        )
