"""Custom fields reach customers and vendors.

Every declared entity type has had a value table since `20260810_0063` and
`AttributeService` has stored and returned values for all of them -- but only
`ProductService` called it, so a field an administrator defined for a
customer was accepted by the catalogue and never offered by the form or
saved by the API. These pin the last mile for the two masters that needed it
first: the write on create, the partial rule on update (absent leaves them
alone, sent replaces them), the mandatory refusal, the response carrying the
stored values, and the route that tells a form which fields to offer.
"""

# ruff: noqa: D101,D102,D103

from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.business.api.router import applicable_attribute_definitions
from app.business.models import (
    AttributeDataType,
    AttributeDefinition,
    AttributeEntityType,
)
from app.business.schemas import AttributeValueInput
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import AuthorizationError, ValidationError
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.customers.api.router import _response as customer_response
from app.customers.schemas import CustomerCreate, CustomerUpdate
from app.customers.services import CustomerService
from app.firms.models import Firm
from app.identity.models import UserFirm
from app.vendors.api.router import _response as vendor_response
from app.vendors.schemas import VendorCreate, VendorUpdate
from app.vendors.services import VendorService

_ACTOR = UUID("00000000-0000-0000-0000-0000000000a1")


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _firm(session: Session) -> Firm:
    firm = Firm(
        name="Acme",
        code="ACME",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(firm)
    session.commit()
    return firm


def _definition(
    session: Session,
    code: str,
    entity_type: AttributeEntityType,
    *,
    data_type: AttributeDataType = AttributeDataType.TEXT,
    mandatory: bool = False,
) -> AttributeDefinition:
    row = AttributeDefinition(
        code=code,
        name=code.replace("_", " ").title(),
        entity_type=entity_type.value,
        data_type=data_type.value,
        mandatory=mandatory,
    )
    session.add(row)
    session.commit()
    return row


def _customer(code: str = "C001", **extra: object) -> CustomerCreate:
    return CustomerCreate.model_validate(
        {
            "code": code,
            "name": "Shop One",
            "customer_type": "BUSINESS",
            "currency_code": "INR",
            **extra,
        }
    )


class TestCustomers:
    def test_a_value_is_saved_on_create_and_returned_on_read(self) -> None:
        session = _session()
        firm = _firm(session)
        licence = _definition(session, "DRUG_LICENCE_NO", AttributeEntityType.CUSTOMER)
        service = CustomerService(session)

        customer = service.create(
            _customer(
                attributes=[
                    {"attribute_definition_id": str(licence.id), "value": "DL-4471"}
                ]
            ),
            firm_id=firm.id,
            actor_id=_ACTOR,
        )

        stored = service.attribute_responses(customer)
        assert [(row.attribute_definition_id, row.value_text) for row in stored] == [
            (licence.id, "DL-4471")
        ]
        # And the response every route builds carries it.
        assert customer_response(customer, session).attributes[0].value_text == (
            "DL-4471"
        )

    def test_an_update_that_omits_them_leaves_them_alone(self) -> None:
        session = _session()
        firm = _firm(session)
        licence = _definition(session, "DRUG_LICENCE_NO", AttributeEntityType.CUSTOMER)
        service = CustomerService(session)
        customer = service.create(
            _customer(
                attributes=[
                    {"attribute_definition_id": str(licence.id), "value": "DL-4471"}
                ]
            ),
            firm_id=firm.id,
            actor_id=_ACTOR,
        )

        # A phone-number correction from a form that shows no custom fields.
        service.update(
            customer.id,
            CustomerUpdate.model_validate(
                {
                    "code": "C001",
                    "name": "Shop One",
                    "customer_type": "BUSINESS",
                    "currency_code": "INR",
                    "phone": "+91 98765 43210",
                }
            ),
            firm_scope=firm.id,
            actor_id=_ACTOR,
        )
        assert [r.value_text for r in service.attribute_responses(customer)] == [
            "DL-4471"
        ]

        # Sending them replaces them; an empty list clears.
        service.update(
            customer.id,
            CustomerUpdate.model_validate(
                {
                    "code": "C001",
                    "name": "Shop One",
                    "customer_type": "BUSINESS",
                    "currency_code": "INR",
                    "attributes": [],
                }
            ),
            firm_scope=firm.id,
            actor_id=_ACTOR,
        )
        assert service.attribute_responses(customer) == []

    def test_a_mandatory_field_is_refused_when_missing(self) -> None:
        session = _session()
        firm = _firm(session)
        _definition(
            session, "DRUG_LICENCE_NO", AttributeEntityType.CUSTOMER, mandatory=True
        )

        with pytest.raises(ValidationError, match="Required attributes are missing"):
            CustomerService(session).create(
                _customer(), firm_id=firm.id, actor_id=_ACTOR
            )

    def test_a_vendor_field_does_not_apply_to_a_customer(self) -> None:
        session = _session()
        firm = _firm(session)
        vendor_only = _definition(session, "SUPPLIER_TIER", AttributeEntityType.VENDOR)

        with pytest.raises(ValidationError, match="do not apply to this record"):
            CustomerService(session).create(
                _customer(
                    attributes=[
                        {"attribute_definition_id": str(vendor_only.id), "value": "A"}
                    ]
                ),
                firm_id=firm.id,
                actor_id=_ACTOR,
            )


class TestVendors:
    def test_a_value_is_saved_typed_and_returned(self) -> None:
        session = _session()
        firm = _firm(session)
        tier = _definition(
            session,
            "SUPPLIER_TIER",
            AttributeEntityType.VENDOR,
            data_type=AttributeDataType.NUMBER,
        )
        service = VendorService(session)

        vendor = service.create(
            VendorCreate(
                code="V001",
                name="Supplier One",
                attributes=[
                    AttributeValueInput(attribute_definition_id=tier.id, value=2)
                ],
            ),
            firm_id=firm.id,
            actor_id=_ACTOR,
        )

        stored = service.attribute_responses(vendor)
        assert len(stored) == 1
        assert stored[0].value_number == 2
        assert stored[0].value_text is None
        assert vendor_response(vendor, session).attributes[0].value_number == 2

    def test_none_leaves_them_and_an_empty_list_clears(self) -> None:
        session = _session()
        firm = _firm(session)
        tier = _definition(session, "SUPPLIER_TIER", AttributeEntityType.VENDOR)
        service = VendorService(session)
        vendor = service.create(
            VendorCreate(
                code="V001",
                name="Supplier One",
                attributes=[
                    AttributeValueInput(attribute_definition_id=tier.id, value="gold")
                ],
            ),
            firm_id=firm.id,
            actor_id=_ACTOR,
        )

        service.update(
            vendor.id,
            VendorUpdate(code="V001", name="Supplier One (renamed)"),
            firm_scope=firm.id,
            actor_id=_ACTOR,
        )
        assert [r.value_text for r in service.attribute_responses(vendor)] == ["gold"]

        service.update(
            vendor.id,
            VendorUpdate(code="V001", name="Supplier One", attributes=[]),
            firm_scope=firm.id,
            actor_id=_ACTOR,
        )
        assert service.attribute_responses(vendor) == []


def _principal(user_id: UUID) -> Principal:
    return Principal(
        subject=user_id,
        roles=frozenset({"VIEWER"}),
        permissions=frozenset(),
        claims=TokenClaims(
            sub=str(user_id), type=TokenType.ACCESS, iat=1, exp=4_102_444_800
        ),
    )


def test_a_form_can_ask_which_fields_apply_to_an_entity_type() -> None:
    """Membership of the firm is the whole gate; the answer is per entity type."""
    session = _session()
    firm = _firm(session)
    user_id = uuid4()
    session.add(UserFirm(user_id=user_id, firm_id=firm.id, is_active=True))
    session.commit()
    licence = _definition(
        session, "DRUG_LICENCE_NO", AttributeEntityType.CUSTOMER, mandatory=True
    )
    _definition(session, "SUPPLIER_TIER", AttributeEntityType.VENDOR)

    answer = applicable_attribute_definitions(
        AttributeEntityType.CUSTOMER,
        _principal(user_id),
        session,
        session,
        firm.id,
    ).data

    assert answer.entity_type is AttributeEntityType.CUSTOMER
    assert [d.code for d in answer.definitions] == ["DRUG_LICENCE_NO"]
    assert answer.mandatory_ids == [licence.id]

    # No firm selected: nothing to answer for.
    with pytest.raises(AuthorizationError, match="Select a firm"):
        applicable_attribute_definitions(
            AttributeEntityType.CUSTOMER, _principal(user_id), session, session, None
        )
    # Not a member: refused like every firm read.
    with pytest.raises(AuthorizationError):
        applicable_attribute_definitions(
            AttributeEntityType.CUSTOMER, _principal(uuid4()), session, session, firm.id
        )
