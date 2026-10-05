"""Customer, supplier and product codes from a series (MST-5, decision A67).

A blank code takes the next from the master's own series -- no financial year
and no yearly restart, since a code names the record for good; a typed code
is kept as typed, and the counter steps over one somebody typed ahead of it.
"""

# ruff: noqa: D103

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.customers.services import CustomerService
from app.document_framework.models import DocumentNumberingRule
from app.products.services import ProductService
from app.vendors.schemas import VendorCreate
from app.vendors.services import VendorService
from tests.unit.test_customer_management import _customer_data, _session_factory
from tests.unit.test_customer_management import _firm as _books_firm
from tests.unit.test_product_master import _base_payload


def _setup() -> tuple[Session, object]:
    session = _session_factory()()
    return session, _books_firm(session, "MCS1")


def test_blank_customer_codes_come_from_the_series_in_order() -> None:
    session, firm = _setup()
    service = CustomerService(session)
    actor = uuid4()
    first = service.create(
        _customer_data(code=" ").model_copy(update={"gst_number": None}),
        firm_id=firm.id,  # type: ignore[attr-defined]
        actor_id=actor,
        may_set_standing_discount=True,
    )
    typed = service.create(
        _customer_data(code="CUS-00002").model_copy(update={"gst_number": None}),
        firm_id=firm.id,  # type: ignore[attr-defined]
        actor_id=actor,
        may_set_standing_discount=True,
    )
    third = service.create(
        _customer_data(code="").model_copy(update={"gst_number": None}),
        firm_id=firm.id,  # type: ignore[attr-defined]
        actor_id=actor,
        may_set_standing_discount=True,
    )
    assert first.code == "CUS-00001"
    assert typed.code == "CUS-00002"
    # The counter steps over the code somebody typed ahead of it.
    assert third.code == "CUS-00003"

    rule = session.scalar(
        select(DocumentNumberingRule).where(
            DocumentNumberingRule.code == "CUSTOMER_CODE_DEFAULT"
        )
    )
    assert rule is not None
    assert rule.include_financial_year is False
    assert rule.auto_reset is False


def test_blank_supplier_and_product_codes_have_their_own_series() -> None:
    session, firm = _setup()
    actor = uuid4()
    vendor = VendorService(session).create(
        VendorCreate(name="Supplier One"),
        firm_id=firm.id,  # type: ignore[attr-defined]
        actor_id=actor,
    )
    assert vendor.code == "SUP-00001"

    product = ProductService(session).create_product(
        _base_payload(code=""),
        firm_id=firm.id,  # type: ignore[attr-defined]
        actor_id=actor,
    )
    assert product.code == "PRD-00001"

    typed = ProductService(session).create_product(
        _base_payload(code="tab-500"),
        firm_id=firm.id,  # type: ignore[attr-defined]
        actor_id=actor,
    )
    assert typed.code == "TAB-500"
