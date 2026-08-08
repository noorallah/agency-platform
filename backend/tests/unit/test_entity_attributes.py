"""Configurable-attribute framework tests.

The framework is exercised through ``ProductAttributeValue``, the first module
table built on :class:`AttributeValueMixin`. Definitions targeting other entity
types are used to prove scoping: a definition for one entity type must never be
storable against another.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.business.models import (
    AttributeDataType,
    AttributeDefinition,
    AttributeEntityType,
    BusinessProfile,
    FirmBusinessProfile,
)
from app.business.services import AttributeInput, AttributeService
from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.firms.models import Firm
from app.products.models import Product, ProductAttributeValue


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _firm(session: Session, code: str = "ACME") -> Firm:
    firm = Firm(
        name=f"{code} Firm",
        code=code,
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(firm)
    session.commit()
    return firm


def _product(session: Session, firm: Firm, code: str = "SKU-1") -> Product:
    """Create an owning product: the value table has a real foreign key."""
    row = Product(
        firm_id=firm.id,
        code=code,
        name=f"Product {code}",
        product_type="STOCK_ITEM",
        status="ACTIVE",
    )
    session.add(row)
    session.commit()
    return row


def _profile(
    session: Session, code: str, *, is_default: bool = False
) -> BusinessProfile:
    profile = BusinessProfile(
        code=code,
        name=code.title(),
        industry_type=code,
        status="ACTIVE",
        is_default=is_default,
    )
    session.add(profile)
    session.commit()
    return profile


def _assign(session: Session, firm: Firm, profile: BusinessProfile) -> None:
    session.add(
        FirmBusinessProfile(
            firm_id=firm.id,
            business_profile_id=profile.id,
            is_active=True,
            effective_from=date(2026, 4, 1),
        )
    )
    session.commit()


def _definition(
    session: Session,
    code: str,
    *,
    entity_type: AttributeEntityType = AttributeEntityType.PRODUCT,
    data_type: AttributeDataType = AttributeDataType.TEXT,
    mandatory: bool = False,
    profile: BusinessProfile | None = None,
) -> AttributeDefinition:
    row = AttributeDefinition(
        code=code,
        name=code.replace("_", " ").title(),
        entity_type=entity_type.value,
        data_type=data_type.value,
        mandatory=mandatory,
        applicable_business_profile_id=profile.id if profile else None,
    )
    session.add(row)
    session.commit()
    return row


def test_a_record_can_carry_a_configured_custom_field() -> None:
    """A field defined by an administrator is stored against a record."""
    session = _session()
    firm = _firm(session)
    product = _product(session, firm)
    licence = _definition(session, "DRUG_LICENCE_NO")
    service = AttributeService(session)

    service.replace_values(
        ProductAttributeValue,
        product.id,
        [AttributeInput(attribute_definition_id=licence.id, value="DL-4471")],
        firm_id=firm.id,
        actor_id=uuid4(),
    )
    session.commit()

    stored = service.values_for(ProductAttributeValue, product.id)
    assert len(stored) == 1
    assert stored[0].definition.code == "DRUG_LICENCE_NO"
    assert stored[0].value == "DL-4471"


def test_definitions_are_scoped_by_entity_type() -> None:
    """A customer field never appears among a product's definitions."""
    session = _session()
    firm = _firm(session)
    _definition(session, "SHELF_LIFE_DAYS")
    _definition(session, "CREDIT_NOTES", entity_type=AttributeEntityType.CUSTOMER)
    service = AttributeService(session)

    products = service.definitions_for(
        AttributeEntityType.PRODUCT.value, firm_id=firm.id
    )
    customers = service.definitions_for(
        AttributeEntityType.CUSTOMER.value, firm_id=firm.id
    )
    assert [row.code for row in products] == ["SHELF_LIFE_DAYS"]
    assert [row.code for row in customers] == ["CREDIT_NOTES"]


def test_attribute_from_another_entity_type_is_rejected() -> None:
    """A customer field cannot be stored against a product."""
    session = _session()
    firm = _firm(session)
    product = _product(session, firm)
    customer_attr = _definition(
        session, "CREDIT_NOTES", entity_type=AttributeEntityType.CUSTOMER
    )
    with pytest.raises(ValidationError, match="do not apply to this record"):
        AttributeService(session).replace_values(
            ProductAttributeValue,
            product.id,
            [AttributeInput(attribute_definition_id=customer_attr.id, value="x")],
            firm_id=firm.id,
            actor_id=uuid4(),
        )


def test_definitions_are_scoped_by_business_profile() -> None:
    """A pharmacy-only field is invisible to a food firm."""
    session = _session()
    pharmacy = _profile(session, "PHARMACY")
    food = _profile(session, "FOOD")
    pharma_firm = _firm(session, "MEDI")
    food_firm = _firm(session, "FOOD")
    _assign(session, pharma_firm, pharmacy)
    _assign(session, food_firm, food)

    _definition(session, "DRUG_LICENCE_NO", profile=pharmacy)
    _definition(session, "GST_NOTES")
    service = AttributeService(session)

    pharma_codes = [
        row.code
        for row in service.definitions_for(
            AttributeEntityType.PRODUCT.value, firm_id=pharma_firm.id
        )
    ]
    food_codes = [
        row.code
        for row in service.definitions_for(
            AttributeEntityType.PRODUCT.value, firm_id=food_firm.id
        )
    ]
    assert pharma_codes == ["DRUG_LICENCE_NO", "GST_NOTES"]
    assert food_codes == ["GST_NOTES"]


def test_values_are_stored_in_typed_columns() -> None:
    """Each data type lands in the column a report can filter on."""
    session = _session()
    firm = _firm(session)
    product = _product(session, firm)
    text = _definition(session, "NOTE")
    number = _definition(session, "LEAD_DAYS", data_type=AttributeDataType.NUMBER)
    when = _definition(session, "AUDITED_ON", data_type=AttributeDataType.DATE)
    flag = _definition(session, "APPROVED", data_type=AttributeDataType.BOOLEAN)

    AttributeService(session).replace_values(
        ProductAttributeValue,
        product.id,
        [
            AttributeInput(attribute_definition_id=text.id, value="preferred"),
            AttributeInput(attribute_definition_id=number.id, value="7.5"),
            AttributeInput(attribute_definition_id=when.id, value="2026-06-30"),
            AttributeInput(attribute_definition_id=flag.id, value=True),
        ],
        firm_id=firm.id,
        actor_id=uuid4(),
    )
    session.commit()

    rows = {
        row.attribute_definition_id: row
        for row in session.scalars(select(ProductAttributeValue)).all()
    }
    assert rows[text.id].value_text == "preferred"
    assert rows[number.id].value_number == Decimal("7.5")
    assert rows[when.id].value_date == date(2026, 6, 30)
    assert rows[flag.id].value_boolean is True
    # Only the matching column is populated.
    assert rows[number.id].value_text is None
    assert rows[flag.id].value_number is None
    # The value carries a real reference to its owner.
    assert rows[text.id].product_id == product.id


def test_wrong_type_is_rejected_with_the_attribute_named() -> None:
    """A mistyped value fails validation rather than being coerced to text."""
    session = _session()
    firm = _firm(session)
    product = _product(session, firm)
    number = _definition(session, "LEAD_DAYS", data_type=AttributeDataType.NUMBER)
    with pytest.raises(ValidationError, match="LEAD_DAYS expects a number"):
        AttributeService(session).replace_values(
            ProductAttributeValue,
            product.id,
            [AttributeInput(attribute_definition_id=number.id, value="soon")],
            firm_id=firm.id,
            actor_id=uuid4(),
        )


def test_mandatory_attribute_must_be_supplied() -> None:
    """A mandatory definition blocks a save that omits it."""
    session = _session()
    firm = _firm(session)
    product = _product(session, firm)
    required = _definition(session, "FSSAI_NO", mandatory=True)
    service = AttributeService(session)

    with pytest.raises(ValidationError, match="Required attributes are missing"):
        service.replace_values(
            ProductAttributeValue,
            product.id,
            [],
            firm_id=firm.id,
            actor_id=uuid4(),
        )
    service.replace_values(
        ProductAttributeValue,
        product.id,
        [AttributeInput(attribute_definition_id=required.id, value="FS-1")],
        firm_id=firm.id,
        actor_id=uuid4(),
    )


def test_replacing_values_clears_the_ones_left_out() -> None:
    """replace_values is a full replacement, not a merge."""
    session = _session()
    firm = _firm(session)
    product = _product(session, firm)
    first = _definition(session, "NOTE_A")
    second = _definition(session, "NOTE_B")
    service = AttributeService(session)
    actor = uuid4()

    service.replace_values(
        ProductAttributeValue,
        product.id,
        [
            AttributeInput(attribute_definition_id=first.id, value="one"),
            AttributeInput(attribute_definition_id=second.id, value="two"),
        ],
        firm_id=firm.id,
        actor_id=actor,
    )
    session.commit()
    assert len(service.values_for(ProductAttributeValue, product.id)) == 2

    service.replace_values(
        ProductAttributeValue,
        product.id,
        [AttributeInput(attribute_definition_id=first.id, value="updated")],
        firm_id=firm.id,
        actor_id=actor,
    )
    session.commit()
    remaining = service.values_for(ProductAttributeValue, product.id)
    assert [row.definition.code for row in remaining] == ["NOTE_A"]
    assert remaining[0].value == "updated"


def test_duplicate_submission_is_rejected() -> None:
    """The same attribute twice in one payload is a client error."""
    session = _session()
    firm = _firm(session)
    product = _product(session, firm)
    definition = _definition(session, "NOTE")
    with pytest.raises(ValidationError, match="more than once"):
        AttributeService(session).replace_values(
            ProductAttributeValue,
            product.id,
            [
                AttributeInput(attribute_definition_id=definition.id, value="a"),
                AttributeInput(attribute_definition_id=definition.id, value="b"),
            ],
            firm_id=firm.id,
            actor_id=uuid4(),
        )


def test_values_for_many_avoids_a_query_per_record() -> None:
    """Bulk reads group values by owning record."""
    session = _session()
    firm = _firm(session)
    definition = _definition(session, "NOTE")
    service = AttributeService(session)
    products = [_product(session, firm, "SKU-1"), _product(session, firm, "SKU-2")]
    for index, product in enumerate(products):
        service.replace_values(
            ProductAttributeValue,
            product.id,
            [AttributeInput(attribute_definition_id=definition.id, value=f"n{index}")],
            firm_id=firm.id,
            actor_id=uuid4(),
        )
    session.commit()

    ids = [product.id for product in products]
    grouped = service.values_for_many(ProductAttributeValue, ids)
    assert set(grouped) == set(ids)
    assert grouped[ids[0]][0].value == "n0"
    assert grouped[ids[1]][0].value == "n1"
    assert service.values_for_many(ProductAttributeValue, []) == {}


def test_datetime_is_narrowed_to_a_date() -> None:
    """A datetime submitted for a DATE attribute stores its date part."""
    session = _session()
    firm = _firm(session)
    product = _product(session, firm)
    when = _definition(session, "AUDITED_ON", data_type=AttributeDataType.DATE)
    AttributeService(session).replace_values(
        ProductAttributeValue,
        product.id,
        [
            AttributeInput(
                attribute_definition_id=when.id, value=datetime(2026, 6, 30, 14, 5)
            )
        ],
        firm_id=firm.id,
        actor_id=uuid4(),
    )
    session.commit()
    stored = AttributeService(session).values_for(ProductAttributeValue, product.id)
    assert stored[0].value == date(2026, 6, 30)


def test_disabling_a_definition_stops_new_data_without_blocking_edits() -> None:
    """A deactivated field must not trap records that already carry a value.

    ``replace_values`` is a full replacement, so an edit form resubmits
    everything it wants to keep. If a disabled attribute were rejected the
    record could not be edited at all; if it were silently dropped the user
    would lose a value still visible on screen.
    """
    session = _session()
    firm = _firm(session)
    existing_product = _product(session, firm, "SKU-1")
    fresh_product = _product(session, firm, "SKU-2")
    definition = _definition(session, "FSSAI_NO")
    service = AttributeService(session)
    actor = uuid4()

    service.replace_values(
        ProductAttributeValue,
        existing_product.id,
        [AttributeInput(attribute_definition_id=definition.id, value="FS-1")],
        firm_id=firm.id,
        actor_id=actor,
    )
    session.commit()

    definition.is_active = False
    session.commit()

    # No longer offered or required for anything new.
    assert (
        service.definitions_for(AttributeEntityType.PRODUCT.value, firm_id=firm.id)
        == []
    )
    assert definition.id not in service.mandatory_ids(
        AttributeEntityType.PRODUCT.value, firm_id=firm.id
    )
    # Still readable on the record that has it.
    assert service.values_for(ProductAttributeValue, existing_product.id)[0].value == (
        "FS-1"
    )
    # That record stays editable.
    service.replace_values(
        ProductAttributeValue,
        existing_product.id,
        [AttributeInput(attribute_definition_id=definition.id, value="FS-2")],
        firm_id=firm.id,
        actor_id=actor,
    )
    session.commit()
    assert service.values_for(ProductAttributeValue, existing_product.id)[0].value == (
        "FS-2"
    )
    # But it cannot be set on a record that never had it.
    with pytest.raises(ValidationError, match="do not apply to this record"):
        service.replace_values(
            ProductAttributeValue,
            fresh_product.id,
            [AttributeInput(attribute_definition_id=definition.id, value="FS-9")],
            firm_id=firm.id,
            actor_id=actor,
        )


def test_a_disabled_value_can_still_be_cleared() -> None:
    """Omitting a disabled attribute removes it, so records can be tidied."""
    session = _session()
    firm = _firm(session)
    product = _product(session, firm)
    definition = _definition(session, "LEGACY_CODE")
    service = AttributeService(session)
    actor = uuid4()

    service.replace_values(
        ProductAttributeValue,
        product.id,
        [AttributeInput(attribute_definition_id=definition.id, value="old")],
        firm_id=firm.id,
        actor_id=actor,
    )
    session.commit()
    definition.is_active = False
    session.commit()

    service.replace_values(
        ProductAttributeValue, product.id, [], firm_id=firm.id, actor_id=actor
    )
    session.commit()
    assert service.values_for(ProductAttributeValue, product.id) == []
