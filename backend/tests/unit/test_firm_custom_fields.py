"""A firm keeps its own custom fields beside the shared catalogue (MST-8).

Several firms share ``firm_shared``, so a definition there used to reach every
one of them. A row with ``firm_id`` is now that firm's own: offered on its
forms and nobody else's, and changed only by its administrator. A row without
one is the platform's shared catalogue -- offered to every firm and read-only
to them.
"""

# ruff: noqa: D103

from datetime import date
from uuid import UUID

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.business.api.router import (
    create_firm_custom_field,
    create_firm_custom_field_rule,
    delete_firm_custom_field,
    delete_firm_custom_field_rule,
    list_firm_custom_field_rules,
    list_firm_custom_fields,
    update_firm_custom_field,
)
from app.business.models import (
    AttributeDataType,
    AttributeDefinition,
    AttributeEntityType,
)
from app.business.schemas import (
    AttributeDefinitionCreate,
    AttributeDefinitionUpdate,
    CategoryAttributeRuleCreate,
)
from app.business.services import AttributeService, BusinessProfileFrameworkService
from app.common.scope import ResolvedFirmScope
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import ConflictError, ResourceNotFoundError, ValidationError
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.firms.models import Firm
from app.identity.system_seed import PERMISSION_GROUPS, ROLE_PERMISSION_CODES

_ACTOR = UUID("00000000-0000-0000-0000-0000000000a1")


def _session() -> Session:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _scope(firm_id: UUID) -> ResolvedFirmScope:
    principal = Principal(
        subject=_ACTOR,
        roles=frozenset(),
        permissions=frozenset({"CUSTOM_FIELD_VIEW", "CUSTOM_FIELD_MANAGE"}),
        claims=TokenClaims(
            sub=str(_ACTOR), type=TokenType.ACCESS, iat=1, exp=4_102_444_800, roles=[]
        ),
    )
    return ResolvedFirmScope(principal=principal, firm_id=firm_id)


def _firm(session: Session, code: str) -> UUID:
    firm = Firm(
        name=code.title(),
        code=code,
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(firm)
    session.flush()
    return firm.id


def _setup() -> tuple[Session, UUID, UUID, AttributeDefinition]:
    """Two firms in one store and one shared field."""
    session = _session()
    acme, beta = _firm(session, "ACME"), _firm(session, "BETA")
    shared = AttributeDefinition(
        code="FSSAI_LICENCE",
        name="FSSAI licence",
        entity_type=AttributeEntityType.CUSTOMER,
        data_type=AttributeDataType.TEXT,
    )
    session.add(shared)
    session.commit()
    return session, acme, beta, shared


def _create(
    session: Session, firm_id: UUID, code: str = "ROUTE_DAY"
) -> AttributeDefinition:
    data = AttributeDefinitionCreate(
        code=code,
        name="Route day",
        entity_type=AttributeEntityType.CUSTOMER,
        data_type=AttributeDataType.TEXT,
    )
    response = create_firm_custom_field(data, _scope(firm_id), session)
    assert response.data is not None
    row = session.get(AttributeDefinition, response.data.id)
    assert row is not None
    return row


def _rename(name: str) -> AttributeDefinitionUpdate:
    """Return the update payload for ROUTE_DAY under a new name."""
    return AttributeDefinitionUpdate(
        code="ROUTE_DAY",
        name=name,
        entity_type=AttributeEntityType.CUSTOMER,
        data_type=AttributeDataType.TEXT,
    )


def test_a_firms_field_reaches_its_own_forms_and_no_other_firms() -> None:
    session, acme, beta, _ = _setup()
    _create(session, acme)
    service = AttributeService(session)

    acme_codes = {
        row.code
        for row in service.definitions_for(AttributeEntityType.CUSTOMER, firm_id=acme)
    }
    beta_codes = {
        row.code
        for row in service.definitions_for(AttributeEntityType.CUSTOMER, firm_id=beta)
    }

    assert acme_codes == {"FSSAI_LICENCE", "ROUTE_DAY"}
    assert beta_codes == {"FSSAI_LICENCE"}


def test_the_firm_list_shows_its_own_and_the_shared_but_not_another_firms() -> None:
    session, acme, beta, _ = _setup()
    _create(session, acme)
    _create(session, beta, code="BEAT_CODE")

    listed = list_firm_custom_fields(_scope(acme), session).data or []

    assert [(row.code, row.firm_id) for row in listed] == [
        ("FSSAI_LICENCE", None),
        ("ROUTE_DAY", acme),
    ]


def test_the_platform_catalogue_lists_only_the_shared_fields() -> None:
    session, acme, _, _ = _setup()
    _create(session, acme)

    rows, total = BusinessProfileFrameworkService(session).list_attributes(
        page=1, page_size=50, search=None, sort_by="code", descending=False
    )

    assert [row.code for row in rows] == ["FSSAI_LICENCE"]
    assert total == 1


def test_two_firms_may_use_the_same_code_but_not_a_shared_one() -> None:
    session, acme, beta, _ = _setup()
    _create(session, acme)
    _create(session, beta)  # its own ROUTE_DAY: no clash with ACME's

    with pytest.raises(ConflictError):
        _create(session, acme)
    with pytest.raises(ConflictError):
        _create(session, acme, code="FSSAI_LICENCE")


def test_a_shared_field_is_read_only_to_a_firm() -> None:
    session, acme, _, shared = _setup()

    with pytest.raises(ResourceNotFoundError):
        update_firm_custom_field(shared.id, _rename("Mine now"), _scope(acme), session)
    with pytest.raises(ResourceNotFoundError):
        delete_firm_custom_field(shared.id, _scope(acme), session)


def test_another_firms_field_cannot_be_changed_or_deleted() -> None:
    session, acme, beta, _ = _setup()
    theirs = _create(session, beta)

    with pytest.raises(ResourceNotFoundError):
        update_firm_custom_field(theirs.id, _rename("X"), _scope(acme), session)
    with pytest.raises(ResourceNotFoundError):
        delete_firm_custom_field(theirs.id, _scope(acme), session)


def test_an_own_field_is_renamed_and_soft_deleted() -> None:
    session, acme, _, _ = _setup()
    own = _create(session, acme)

    update_firm_custom_field(own.id, _rename("Visit day"), _scope(acme), session)
    session.refresh(own)
    assert (own.name, own.code, own.data_type) == ("Visit day", "ROUTE_DAY", "TEXT")

    delete_firm_custom_field(own.id, _scope(acme), session)
    session.refresh(own)
    assert own.is_deleted
    # The code is free again once the row is gone.
    assert _create(session, acme).code == "ROUTE_DAY"


def test_a_firm_rule_makes_its_field_mandatory_only_for_that_firm() -> None:
    session, acme, beta, shared = _setup()
    response = create_firm_custom_field_rule(
        CategoryAttributeRuleCreate(
            category_code="dairy", attribute_definition_id=shared.id
        ),
        _scope(acme),
        session,
    )
    assert response.data is not None
    service = AttributeService(session)

    acme_required = service.mandatory_ids(
        AttributeEntityType.CUSTOMER, firm_id=acme, category_code="DAIRY"
    )
    beta_required = service.mandatory_ids(
        AttributeEntityType.CUSTOMER, firm_id=beta, category_code="DAIRY"
    )
    assert acme_required == {shared.id}
    assert beta_required == set()

    assert [
        r.id for r in list_firm_custom_field_rules(_scope(beta), session).data or []
    ] == []
    with pytest.raises(ResourceNotFoundError):
        delete_firm_custom_field_rule(response.data.id, _scope(beta), session)
    delete_firm_custom_field_rule(response.data.id, _scope(acme), session)
    assert list_firm_custom_field_rules(_scope(acme), session).data == []


def test_a_rule_cannot_name_another_firms_field() -> None:
    session, acme, beta, _ = _setup()
    theirs = _create(session, beta)

    with pytest.raises(ValidationError):
        create_firm_custom_field_rule(
            CategoryAttributeRuleCreate(
                category_code="DAIRY", attribute_definition_id=theirs.id
            ),
            _scope(acme),
            session,
        )


def test_the_firm_administrator_holds_both_codes_and_the_manager_neither() -> None:
    codes = set(PERMISSION_GROUPS["custom_fields"])

    assert codes <= set(ROLE_PERMISSION_CODES["FIRM_ADMIN"])
    assert not codes & set(ROLE_PERMISSION_CODES["FIRM_MANAGER"])
