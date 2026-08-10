"""Custom fields on the master objects beyond products.

``AttributeEntityType`` declared CUSTOMER, VENDOR, BRANCH and WAREHOUSE from the
start, but only ``product_attribute_values`` existed. A definition could target
those objects and had nowhere to store a value, so custom fields were unusable on
four of the five objects that advertised them. Tax profiles and units of measure
are new targets.

``test_entity_attributes`` covers the framework's behaviour through products.
This file covers what is specific to the new tables: that each one round-trips,
and that a unit of measure -- whose owning row is shared by every firm in a store
rather than owned by one -- keeps each firm's annotations to itself.
"""

from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.branches.models import (
    Branch,
    BranchAttributeValue,
    Warehouse,
    WarehouseAttributeValue,
)
from app.business.models import (
    AttributeDataType,
    AttributeDefinition,
    AttributeEntityType,
    AttributeValueBase,
)
from app.business.services import AttributeInput, AttributeService
from app.core.database.base import Base
from app.customers.models import Customer, CustomerAttributeValue
from app.firms.models import Firm
from app.tax.models import TaxProfile, TaxProfileAttributeValue, TaxSystem
from app.uom.models import Uom, UomAttributeValue
from app.vendors.models import Vendor, VendorAttributeValue


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


def _definition(
    session: Session,
    code: str,
    entity_type: AttributeEntityType,
    *,
    data_type: AttributeDataType = AttributeDataType.TEXT,
) -> AttributeDefinition:
    row = AttributeDefinition(
        code=code,
        name=code.replace("_", " ").title(),
        entity_type=entity_type.value,
        data_type=data_type.value,
        mandatory=False,
    )
    session.add(row)
    session.commit()
    return row


def _owner(session: Session, firm: Firm, entity_type: AttributeEntityType) -> UUID:
    """Create the record a custom field will hang off, whatever its type."""
    if entity_type is AttributeEntityType.CUSTOMER:
        row: object = Customer(
            firm_id=firm.id,
            code="CUST-1",
            customer_type="BUSINESS",
            name="Acme Retail",
            display_name="Acme Retail",
            currency_code="INR",
            status="ACTIVE",
        )
    elif entity_type is AttributeEntityType.VENDOR:
        row = Vendor(
            firm_id=firm.id,
            code="VEND-1",
            name="Bulk Supplies",
            display_name="Bulk Supplies",
        )
    elif entity_type is AttributeEntityType.BRANCH:
        row = Branch(
            firm_id=firm.id,
            code="BR-1",
            name="Head Office",
            display_name="Head Office",
        )
    elif entity_type is AttributeEntityType.WAREHOUSE:
        branch = Branch(
            firm_id=firm.id, code="BR-W", name="Depot", display_name="Depot"
        )
        session.add(branch)
        session.commit()
        row = Warehouse(
            firm_id=firm.id,
            branch_id=branch.id,
            code="WH-1",
            name="Main",
            display_name="Main",
        )
    elif entity_type is AttributeEntityType.TAX_PROFILE:
        system = TaxSystem(firm_id=firm.id, code="GST", name="GST", display_name="GST")
        session.add(system)
        session.commit()
        row = TaxProfile(
            firm_id=firm.id,
            tax_system_id=system.id,
            code="GST_18",
            name="GST 18%",
            label="GST 18%",
            status="ACTIVE",
        )
    else:
        row = Uom(code="BOX", name="Box", dimension="COUNT", status="ACTIVE")
    session.add(row)
    session.commit()
    return row.id  # type: ignore[attr-defined,no-any-return]


#: Every object that gained a value table, with the model storing its values.
_TARGETS: list[tuple[AttributeEntityType, type[AttributeValueBase]]] = [
    (AttributeEntityType.CUSTOMER, CustomerAttributeValue),
    (AttributeEntityType.VENDOR, VendorAttributeValue),
    (AttributeEntityType.BRANCH, BranchAttributeValue),
    (AttributeEntityType.WAREHOUSE, WarehouseAttributeValue),
    (AttributeEntityType.TAX_PROFILE, TaxProfileAttributeValue),
    (AttributeEntityType.UOM, UomAttributeValue),
]


@pytest.mark.parametrize(
    ("entity_type", "model"), _TARGETS, ids=[t.value for t, _ in _TARGETS]
)
def test_each_master_object_can_carry_a_custom_field(
    entity_type: AttributeEntityType, model: type[AttributeValueBase]
) -> None:
    """A field an administrator defines is stored against the record."""
    session = _session()
    firm = _firm(session)
    owner_id = _owner(session, firm, entity_type)
    definition = _definition(session, "EXTERNAL_REF", entity_type)
    service = AttributeService(session)

    service.replace_values(
        model,
        owner_id,
        [AttributeInput(attribute_definition_id=definition.id, value="REF-99")],
        firm_id=firm.id,
        actor_id=uuid4(),
    )
    session.commit()

    stored = service.values_for(model, owner_id, firm_id=firm.id)
    assert [(item.definition.code, item.value) for item in stored] == [
        ("EXTERNAL_REF", "REF-99")
    ]


@pytest.mark.parametrize(
    ("entity_type", "model"), _TARGETS, ids=[t.value for t, _ in _TARGETS]
)
def test_a_definition_for_another_object_is_rejected(
    entity_type: AttributeEntityType, model: type[AttributeValueBase]
) -> None:
    """Entity targeting is enforced, so a field cannot land on the wrong table."""
    session = _session()
    firm = _firm(session)
    owner_id = _owner(session, firm, entity_type)
    # PRODUCT for everything else; CUSTOMER when the table under test is
    # products' own neighbour, so the definition is always the wrong one.
    wrong = (
        AttributeEntityType.CUSTOMER
        if entity_type is AttributeEntityType.PRODUCT
        else AttributeEntityType.PRODUCT
    )
    definition = _definition(session, "WRONG_TARGET", wrong)

    with pytest.raises(Exception, match="do not apply"):
        AttributeService(session).replace_values(
            model,
            owner_id,
            [AttributeInput(attribute_definition_id=definition.id, value="x")],
            firm_id=firm.id,
            actor_id=uuid4(),
        )


def test_two_firms_annotate_one_shared_unit_independently() -> None:
    """A unit of measure is shared; its custom fields are not.

    ``uoms`` has no ``firm_id`` and a single row serves every firm in a shared
    store. Keyed on the unit alone, the first firm to save would have claimed the
    attribute and locked the others out, and a read would have returned another
    firm's answer. Both are what this asserts against.
    """
    session = _session()
    first = _firm(session, "FIRST")
    second = _firm(session, "SECOND")
    unit = Uom(code="CASE", name="Case", dimension="COUNT", status="ACTIVE")
    session.add(unit)
    session.commit()
    definition = _definition(session, "PACK_BARCODE", AttributeEntityType.UOM)
    service = AttributeService(session)

    for firm, value in ((first, "8901234"), (second, "7005566")):
        service.replace_values(
            UomAttributeValue,
            unit.id,
            [AttributeInput(attribute_definition_id=definition.id, value=value)],
            firm_id=firm.id,
            actor_id=uuid4(),
        )
        session.commit()

    assert [
        item.value
        for item in service.values_for(UomAttributeValue, unit.id, firm_id=first.id)
    ] == ["8901234"]
    assert [
        item.value
        for item in service.values_for(UomAttributeValue, unit.id, firm_id=second.id)
    ] == ["7005566"]


def test_one_firm_cannot_set_the_same_unit_attribute_twice() -> None:
    """Uniqueness still holds within a firm, which is what it is there for."""
    session = _session()
    firm = _firm(session)
    unit = Uom(code="CRATE", name="Crate", dimension="COUNT", status="ACTIVE")
    session.add(unit)
    session.commit()
    definition = _definition(session, "PACK_BARCODE", AttributeEntityType.UOM)

    session.add_all(
        UomAttributeValue(
            firm_id=firm.id,
            uom_id=unit.id,
            attribute_definition_id=definition.id,
            value_text=text,
        )
        for text in ("first", "second")
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_saving_one_firms_unit_fields_leaves_the_others_alone() -> None:
    """Replacing values must not clear a value that belongs to another firm.

    ``replace_values`` treats anything not resubmitted as cleared. Scoped only by
    owner, one firm saving a unit's fields would have soft-deleted every other
    firm's values for that same unit.
    """
    session = _session()
    first = _firm(session, "FIRST")
    second = _firm(session, "SECOND")
    unit = Uom(code="PALLET", name="Pallet", dimension="COUNT", status="ACTIVE")
    session.add(unit)
    session.commit()
    definition = _definition(session, "PACK_BARCODE", AttributeEntityType.UOM)
    service = AttributeService(session)

    service.replace_values(
        UomAttributeValue,
        unit.id,
        [AttributeInput(attribute_definition_id=definition.id, value="keep-me")],
        firm_id=first.id,
        actor_id=uuid4(),
    )
    session.commit()

    # The second firm submits nothing for this unit, clearing only its own.
    service.replace_values(
        UomAttributeValue, unit.id, [], firm_id=second.id, actor_id=uuid4()
    )
    session.commit()

    survivors = service.values_for(UomAttributeValue, unit.id, firm_id=first.id)
    assert [item.value for item in survivors] == ["keep-me"]
