"""A custom field follows the kind of record, never the firm's profile.

Backlog 89, step 5. A rule can tie a field to a goods type, a customer group
or a supplier type: the field is then offered on records of the kinds its
rules name and on no other, and is compulsory where the rule says so. A firm
can switch a field of the shared catalogue off for itself, which hides it and
keeps every value. The business profile takes no part in either.
"""

# ruff: noqa: D103

from datetime import date
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError as SchemaError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.business.api.router import (
    applicable_attribute_definitions,
    list_firm_custom_fields,
    set_firm_custom_field_use,
)
from app.business.models import (
    AttributeDefinition,
    AttributeEntityType,
    BusinessProfile,
    CategoryAttributeRule,
    FirmAttributeSwitch,
    FirmBusinessProfile,
)
from app.business.schemas import (
    AttributeDefinitionCreate,
    CategoryAttributeRuleCreate,
    FirmFieldUse,
)
from app.business.services import (
    AttributeService,
    BusinessProfileFrameworkService,
    RecordKind,
)
from app.business.services.firm_custom_fields import FirmCustomFieldService
from app.common.audit.models.audit_log import AuditLog
from app.common.scope import ResolvedFirmScope
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.customers.models import CustomerAttributeValue, CustomerGroup
from app.customers.schemas import CustomerCreate, CustomerUpdate
from app.customers.services import CustomerService
from app.firms.models import Firm
from app.identity.models import UserFirm
from app.identity.system_seed import ROLE_PERMISSION_CODES
from app.products.models import GoodsType
from app.vendors.models import VendorType
from app.vendors.schemas import VendorCreate
from app.vendors.services import VendorService

_ACTOR = UUID("00000000-0000-0000-0000-0000000000a1")
PRODUCT = AttributeEntityType.PRODUCT
CUSTOMER = AttributeEntityType.CUSTOMER
VENDOR = AttributeEntityType.VENDOR


def _session() -> Session:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _firm(session: Session, code: str = "ACME") -> UUID:
    firm = Firm(
        name=code.title(),
        code=code,
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(firm)
    session.commit()
    return firm.id


def _field(
    session: Session,
    code: str,
    entity: AttributeEntityType,
    *,
    firm_id: UUID | None = None,
    mandatory: bool = False,
) -> AttributeDefinition:
    row = AttributeDefinition(
        code=code,
        name=code.replace("_", " ").title(),
        entity_type=entity.value,
        data_type="TEXT",
        mandatory=mandatory,
        firm_id=firm_id,
    )
    session.add(row)
    session.commit()
    return row


def _group(session: Session, firm_id: UUID, code: str) -> CustomerGroup:
    row = CustomerGroup(firm_id=firm_id, code=code, name=code.title())
    session.add(row)
    session.commit()
    return row


def _vendor_type(session: Session, firm_id: UUID, code: str) -> VendorType:
    row = VendorType(firm_id=firm_id, code=code, name=code.title())
    session.add(row)
    session.commit()
    return row


def _goods_type(session: Session, code: str, firm_id: UUID | None = None) -> GoodsType:
    row = GoodsType(code=code, name=code.title(), firm_id=firm_id)
    session.add(row)
    session.commit()
    return row


def _scope(firm_id: UUID, *codes: str) -> ResolvedFirmScope:
    principal = Principal(
        subject=_ACTOR,
        roles=frozenset(),
        permissions=frozenset(codes or {"CUSTOM_FIELD_VIEW", "CUSTOM_FIELD_MANAGE"}),
        claims=TokenClaims(
            sub=str(_ACTOR), type=TokenType.ACCESS, iat=1, exp=4_102_444_800, roles=[]
        ),
    )
    return ResolvedFirmScope(principal=principal, firm_id=firm_id)


def _rule(
    session: Session, firm_id: UUID, field: AttributeDefinition, **named: object
) -> CategoryAttributeRule:
    return FirmCustomFieldService(session).create_rule(
        CategoryAttributeRuleCreate.model_validate(
            {"attribute_definition_id": str(field.id), **named}
        ),
        firm_id=firm_id,
        actor_id=_ACTOR,
    )


def _codes(
    session: Session,
    entity: AttributeEntityType,
    firm_id: UUID,
    kind: RecordKind | None = None,
) -> list[str]:
    return [
        row.code
        for row in AttributeService(session).definitions_for(
            entity.value, firm_id=firm_id, kind=kind
        )
    ]


# ----------------------------------------------------------------------
# Products: the goods type
# ----------------------------------------------------------------------


def test_a_product_field_is_shown_and_required_by_goods_type() -> None:
    session = _session()
    firm = _firm(session)
    medicine, paint = _goods_type(session, "MEDICINE"), _goods_type(session, "PAINT")
    schedule = _field(session, "DRUG_SCHEDULE", PRODUCT)
    shade = _field(session, "SHADE_CODE", PRODUCT)
    plain = _field(session, "SHELF_NOTE", PRODUCT)
    _rule(session, firm, schedule, goods_type_id=str(medicine.id), is_mandatory=True)
    _rule(session, firm, shade, goods_type_id=str(paint.id), is_mandatory=False)
    service = AttributeService(session)

    as_medicine = service.applied(
        PRODUCT.value, firm_id=firm, kind=RecordKind(goods_type_id=medicine.id)
    )
    as_paint = service.applied(
        PRODUCT.value, firm_id=firm, kind=RecordKind(goods_type_id=paint.id)
    )
    general = service.applied(PRODUCT.value, firm_id=firm)

    assert [row.code for row in as_medicine.definitions] == [
        "DRUG_SCHEDULE",
        "SHELF_NOTE",
    ]
    assert as_medicine.required == {schedule.id}
    assert [row.code for row in as_paint.definitions] == ["SHADE_CODE", "SHELF_NOTE"]
    assert as_paint.required == set(), "shown on paint, and nobody has to fill it"
    # General: a product with no goods type carries no field tied to one.
    assert [row.code for row in general.definitions] == [plain.code]
    assert general.required == set()


def test_one_field_can_belong_to_two_goods_types() -> None:
    session = _session()
    firm = _firm(session)
    medicine, food = _goods_type(session, "MEDICINE"), _goods_type(session, "FOOD")
    storage = _field(session, "STORAGE_TEMPERATURE", PRODUCT)
    _rule(session, firm, storage, goods_type_id=str(medicine.id), is_mandatory=True)
    _rule(session, firm, storage, goods_type_id=str(food.id), is_mandatory=False)
    service = AttributeService(session)

    assert service.mandatory_ids(
        PRODUCT.value, firm_id=firm, kind=RecordKind(goods_type_id=medicine.id)
    ) == {storage.id}
    assert (
        service.mandatory_ids(
            PRODUCT.value, firm_id=firm, kind=RecordKind(goods_type_id=food.id)
        )
        == set()
    )
    assert _codes(session, PRODUCT, firm, RecordKind(goods_type_id=food.id)) == [
        "STORAGE_TEMPERATURE"
    ]


def test_a_firms_goods_type_rule_stays_in_that_firm() -> None:
    """Several firms share one store, and a rule is its firm's own."""
    session = _session()
    acme, beta = _firm(session, "ACME"), _firm(session, "BETA")
    medicine = _goods_type(session, "MEDICINE")
    schedule = _field(session, "DRUG_SCHEDULE", PRODUCT)
    _rule(session, acme, schedule, goods_type_id=str(medicine.id))

    assert _codes(session, PRODUCT, acme) == []
    # Beta made no rule, so for Beta the field is tied to nothing.
    assert _codes(session, PRODUCT, beta) == ["DRUG_SCHEDULE"]


# ----------------------------------------------------------------------
# Customers and suppliers: the group and the type
# ----------------------------------------------------------------------


def _customer(code: str, **extra: object) -> CustomerCreate:
    return CustomerCreate.model_validate(
        {
            "code": code,
            "name": f"Customer {code}",
            "customer_type": "BUSINESS",
            "currency_code": "INR",
            **extra,
        }
    )


def test_a_customer_field_is_required_for_one_group_and_not_asked_of_another() -> None:
    session = _session()
    firm = _firm(session)
    contractors = _group(session, firm, "CONTRACTORS")
    retailers = _group(session, firm, "RETAILERS")
    registration = _field(session, "CONTRACTOR_REG_NO", CUSTOMER, firm_id=firm)
    _rule(
        session,
        firm,
        registration,
        customer_group_id=str(contractors.id),
        is_mandatory=True,
    )
    service = CustomerService(session)

    # A contractor without it is refused, by name.
    with pytest.raises(ValidationError, match="Required attributes are missing"):
        service.create(
            _customer("C1", customer_group_id=str(contractors.id)),
            firm_id=firm,
            actor_id=_ACTOR,
        )
    session.rollback()
    saved = service.create(
        _customer(
            "C1",
            customer_group_id=str(contractors.id),
            attributes=[
                {"attribute_definition_id": str(registration.id), "value": "CR-77"}
            ],
        ),
        firm_id=firm,
        actor_id=_ACTOR,
    )
    assert [row.value_text for row in service.attribute_responses(saved)] == ["CR-77"]

    # A retailer is not asked, and so is a customer in no group.
    service.create(
        _customer("C2", customer_group_id=str(retailers.id)),
        firm_id=firm,
        actor_id=_ACTOR,
    )
    service.create(_customer("C3"), firm_id=firm, actor_id=_ACTOR)

    # And a retailer may not carry it: the field is not a retailer's.
    with pytest.raises(ValidationError, match="do not apply"):
        service.create(
            _customer(
                "C4",
                customer_group_id=str(retailers.id),
                attributes=[
                    {"attribute_definition_id": str(registration.id), "value": "X"}
                ],
            ),
            firm_id=firm,
            actor_id=_ACTOR,
        )


def test_moving_a_customer_to_another_group_removes_nothing() -> None:
    """The new group's fields are asked at the next save; the old value stays."""
    session = _session()
    firm = _firm(session)
    contractors = _group(session, firm, "CONTRACTORS")
    retailers = _group(session, firm, "RETAILERS")
    registration = _field(session, "CONTRACTOR_REG_NO", CUSTOMER, firm_id=firm)
    shop_act = _field(session, "SHOP_ACT_NO", CUSTOMER, firm_id=firm)
    _rule(session, firm, registration, customer_group_id=str(contractors.id))
    _rule(session, firm, shop_act, customer_group_id=str(retailers.id))
    service = CustomerService(session)
    customer = service.create(
        _customer(
            "C1",
            customer_group_id=str(contractors.id),
            attributes=[
                {"attribute_definition_id": str(registration.id), "value": "CR-77"}
            ],
        ),
        firm_id=firm,
        actor_id=_ACTOR,
    )

    def _move(attributes: list[dict[str, str]] | None) -> None:
        body: dict[str, object] = {
            "code": "C1",
            "name": "Customer C1",
            "customer_type": "BUSINESS",
            "currency_code": "INR",
            "customer_group_id": str(retailers.id),
        }
        if attributes is not None:
            body["attributes"] = attributes
        service.update(
            customer.id,
            CustomerUpdate.model_validate(body),
            firm_scope=firm,
            actor_id=_ACTOR,
        )

    # Moved by a form that sends no custom fields: nothing is touched.
    _move(None)
    assert [row.value_text for row in service.attribute_responses(customer)] == [
        "CR-77"
    ]
    # The form sends the fields: the retailer's is required now ...
    with pytest.raises(ValidationError, match="Required attributes are missing"):
        _move([{"attribute_definition_id": str(registration.id), "value": "CR-77"}])
    session.rollback()
    # ... and the contractor's value, which the record already holds, may
    # still be sent back beside it.
    _move(
        [
            {"attribute_definition_id": str(registration.id), "value": "CR-77"},
            {"attribute_definition_id": str(shop_act.id), "value": "SA-1"},
        ]
    )
    held = session.scalars(
        select(CustomerAttributeValue.value_text).where(
            CustomerAttributeValue.customer_id == customer.id,
            CustomerAttributeValue.is_deleted.is_(False),
        )
    ).all()
    assert sorted(held) == ["CR-77", "SA-1"]


def test_a_supplier_field_is_required_for_one_supplier_type() -> None:
    session = _session()
    firm = _firm(session)
    importer = _vendor_type(session, firm, "IMPORTER")
    local = _vendor_type(session, firm, "LOCAL")
    iec = _field(session, "IMPORT_EXPORT_CODE", VENDOR, firm_id=firm)
    _rule(session, firm, iec, vendor_type_id=str(importer.id), is_mandatory=True)
    service = VendorService(session)

    with pytest.raises(ValidationError, match="Required attributes are missing"):
        service.create(
            VendorCreate.model_validate(
                {"code": "V1", "name": "Importer One", "type_id": str(importer.id)}
            ),
            firm_id=firm,
            actor_id=_ACTOR,
        )
    session.rollback()
    service.create(
        VendorCreate.model_validate(
            {
                "code": "V1",
                "name": "Importer One",
                "type_id": str(importer.id),
                "attributes": [
                    {"attribute_definition_id": str(iec.id), "value": "IEC-9"}
                ],
            }
        ),
        firm_id=firm,
        actor_id=_ACTOR,
    )
    service.create(
        VendorCreate.model_validate(
            {"code": "V2", "name": "Local One", "type_id": str(local.id)}
        ),
        firm_id=firm,
        actor_id=_ACTOR,
    )


def test_the_form_is_told_the_rules_so_it_need_not_ask_again() -> None:
    """One call serves a form whose record changes kind."""
    session = _session()
    firm = _firm(session)
    session.add(UserFirm(user_id=_ACTOR, firm_id=firm, is_active=True))
    contractors = _group(session, firm, "CONTRACTORS")
    registration = _field(session, "CONTRACTOR_REG_NO", CUSTOMER, firm_id=firm)
    always = _field(session, "KYC_REF", CUSTOMER, mandatory=True)
    _rule(
        session,
        firm,
        registration,
        customer_group_id=str(contractors.id),
        is_mandatory=True,
    )

    answer = applicable_attribute_definitions(
        CUSTOMER, _scope(firm).principal, session, session, firm
    ).data

    assert answer is not None
    assert [row.code for row in answer.definitions] == ["CONTRACTOR_REG_NO", "KYC_REF"]
    # Required whatever the group; the tied one only where its rule says.
    assert answer.mandatory_ids == [always.id]
    assert [
        (rule.attribute_definition_id, rule.customer_group_id, rule.is_mandatory)
        for rule in answer.kind_rules
    ] == [(registration.id, contractors.id, True)]


# ----------------------------------------------------------------------
# What a rule may name
# ----------------------------------------------------------------------


def test_a_rule_names_exactly_one_thing() -> None:
    field, group, goods = uuid4(), uuid4(), uuid4()
    with pytest.raises(SchemaError, match="exactly one"):
        CategoryAttributeRuleCreate(attribute_definition_id=field)
    with pytest.raises(SchemaError, match="exactly one"):
        CategoryAttributeRuleCreate(
            attribute_definition_id=field, customer_group_id=group, goods_type_id=goods
        )
    with pytest.raises(SchemaError):
        CategoryAttributeRuleCreate.model_validate(
            {
                "attribute_definition_id": str(field),
                "category_code": "TABLETS",
                "business_profile_id": str(uuid4()),
            }
        )


def test_a_rule_is_refused_a_kind_its_field_does_not_have() -> None:
    session = _session()
    acme, beta = _firm(session, "ACME"), _firm(session, "BETA")
    group = _group(session, acme, "CONTRACTORS")
    others_group = _group(session, beta, "CONTRACTORS")
    others_type = _goods_type(session, "BETA_ONLY", firm_id=beta)
    product_field = _field(session, "SHADE_CODE", PRODUCT)
    customer_field = _field(session, "CONTRACTOR_REG_NO", CUSTOMER)

    with pytest.raises(ValidationError, match="cannot name a customer group"):
        _rule(session, acme, product_field, customer_group_id=str(group.id))
    with pytest.raises(ValidationError, match="cannot name a goods type"):
        _rule(session, acme, customer_field, goods_type_id=str(others_type.id))
    with pytest.raises(ValidationError, match="not this firm's"):
        _rule(session, acme, customer_field, customer_group_id=str(others_group.id))
    with pytest.raises(ValidationError, match="goods type is not one"):
        _rule(session, acme, product_field, goods_type_id=str(others_type.id))

    _rule(session, acme, customer_field, customer_group_id=str(group.id))
    with pytest.raises(ConflictError, match="already exists"):
        _rule(session, acme, customer_field, customer_group_id=str(group.id))
    assert session.scalars(select(CategoryAttributeRule)).all() != []


def test_a_shared_rule_names_only_what_is_shared() -> None:
    session = _session()
    firm = _firm(session)
    group = _group(session, firm, "CONTRACTORS")
    own_type = _goods_type(session, "OWN", firm_id=firm)
    medicine = _goods_type(session, "MEDICINE")
    service = BusinessProfileFrameworkService(session)
    field = service.create_attribute(
        AttributeDefinitionCreate(
            code="DRUG_SCHEDULE", name="Sched", entity_type="PRODUCT", data_type="TEXT"
        ),
        _ACTOR,
    )
    customer_field = service.create_attribute(
        AttributeDefinitionCreate(
            code="KYC_REF", name="KYC", entity_type="CUSTOMER", data_type="TEXT"
        ),
        _ACTOR,
    )

    with pytest.raises(ValidationError, match="each firm's own"):
        service.create_category_rule(
            CategoryAttributeRuleCreate(
                attribute_definition_id=customer_field.id, customer_group_id=group.id
            ),
            _ACTOR,
        )
    with pytest.raises(ValidationError, match="goods type is not one"):
        service.create_category_rule(
            CategoryAttributeRuleCreate(
                attribute_definition_id=field.id, goods_type_id=own_type.id
            ),
            _ACTOR,
        )
    rule = service.create_category_rule(
        CategoryAttributeRuleCreate(
            attribute_definition_id=field.id, goods_type_id=medicine.id
        ),
        _ACTOR,
    )
    with pytest.raises(ConflictError, match="already exists"):
        service.create_category_rule(
            CategoryAttributeRuleCreate(
                attribute_definition_id=field.id, goods_type_id=medicine.id
            ),
            _ACTOR,
        )
    # The shared rule reaches every firm in the store.
    assert _codes(session, PRODUCT, firm) == []
    assert _codes(session, PRODUCT, firm, RecordKind(goods_type_id=medicine.id)) == [
        "DRUG_SCHEDULE"
    ]
    # And the platform's list is the shared rules, not a firm's own.
    _rule(session, firm, field, goods_type_id=str(own_type.id))
    rows, total = service.list_category_rules(1, 20, None, "created_at", False)
    assert (total, [row.id for row in rows]) == (1, [rule.id])


# ----------------------------------------------------------------------
# A firm switches a shared field off
# ----------------------------------------------------------------------


def test_a_firm_switches_a_shared_field_off_and_its_values_are_kept() -> None:
    session = _session()
    acme, beta = _firm(session, "ACME"), _firm(session, "BETA")
    licence = _field(session, "TRADE_LICENCE_NO", CUSTOMER)
    service = CustomerService(session)
    customer = service.create(
        _customer(
            "C1",
            attributes=[{"attribute_definition_id": str(licence.id), "value": "TL-1"}],
        ),
        firm_id=acme,
        actor_id=_ACTOR,
    )

    answer = set_firm_custom_field_use(
        licence.id, FirmFieldUse(is_enabled=False), _scope(acme), session
    ).data
    assert answer is not None and answer.enabled_for_firm is False

    assert _codes(session, CUSTOMER, acme) == []
    assert _codes(session, CUSTOMER, beta) == ["TRADE_LICENCE_NO"], "Acme's choice"
    listed = {
        row.code: row.enabled_for_firm
        for row in list_firm_custom_fields(_scope(acme), session).data or []
    }
    assert listed == {"TRADE_LICENCE_NO": False}
    # Nothing was deleted, and a new customer is no longer offered it.
    assert [row.value_text for row in service.attribute_responses(customer)] == ["TL-1"]
    with pytest.raises(ValidationError, match="do not apply"):
        service.create(
            _customer(
                "C2",
                attributes=[
                    {"attribute_definition_id": str(licence.id), "value": "TL-2"}
                ],
            ),
            firm_id=acme,
            actor_id=_ACTOR,
        )
    session.rollback()

    # On again: the same row, the value still there, and both changes audited.
    set_firm_custom_field_use(
        licence.id, FirmFieldUse(is_enabled=True), _scope(acme), session
    )
    assert _codes(session, CUSTOMER, acme) == ["TRADE_LICENCE_NO"]
    assert len(session.scalars(select(FirmAttributeSwitch)).all()) == 1
    audited = session.scalars(
        select(AuditLog).where(AuditLog.action == "firm_custom_field.use_changed")
    ).all()
    assert [(row.firm_id, row.after_data["is_enabled"]) for row in audited] == [
        (acme, False),
        (acme, True),
    ]
    # Saying "on" to a field that is on writes nothing.
    set_firm_custom_field_use(
        licence.id, FirmFieldUse(is_enabled=True), _scope(acme), session
    )
    assert len(audited) == len(
        session.scalars(
            select(AuditLog).where(AuditLog.action == "firm_custom_field.use_changed")
        ).all()
    )


def test_only_a_shared_field_has_the_switch() -> None:
    session = _session()
    acme, beta = _firm(session, "ACME"), _firm(session, "BETA")
    own = _field(session, "ROUTE_NOTE", CUSTOMER, firm_id=acme)
    theirs = _field(session, "BETA_NOTE", CUSTOMER, firm_id=beta)

    for field in (own, theirs):
        with pytest.raises(ResourceNotFoundError, match="shared list"):
            set_firm_custom_field_use(
                field.id, FirmFieldUse(is_enabled=False), _scope(acme), session
            )
    with pytest.raises(ResourceNotFoundError):
        set_firm_custom_field_use(
            uuid4(), FirmFieldUse(is_enabled=False), _scope(acme), session
        )


def test_who_may_keep_the_fields_and_their_rules() -> None:
    """The firm's administrator, and not the manager under them."""
    assert "CUSTOM_FIELD_MANAGE" in ROLE_PERMISSION_CODES["FIRM_ADMIN"]
    assert "CUSTOM_FIELD_MANAGE" not in ROLE_PERMISSION_CODES["FIRM_MANAGER"]
    assert "CUSTOM_FIELD_MANAGE" not in ROLE_PERMISSION_CODES["SALES_MANAGER"]


def test_a_firm_on_any_profile_is_offered_the_same_fields() -> None:
    """What the profile no longer does."""
    session = _session()
    firm = _firm(session)
    profile = BusinessProfile(
        code="PHARMACY",
        name="Pharmacy",
        industry_type="PHARMACY",
        status="ACTIVE",
        is_default=False,
    )
    session.add(profile)
    session.flush()
    session.add(
        FirmBusinessProfile(
            firm_id=firm,
            business_profile_id=profile.id,
            is_active=True,
            effective_from=date(2026, 4, 1),
        )
    )
    _field(session, "SHADE_CODE", PRODUCT)
    _field(session, "FSSAI_NOTE", PRODUCT)

    assert _codes(session, PRODUCT, firm) == ["FSSAI_NOTE", "SHADE_CODE"]
    assert not hasattr(AttributeDefinition, "applicable_business_profile_id")
    assert not hasattr(CategoryAttributeRule, "business_profile_id")
