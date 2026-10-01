"""Once a custom field holds values, its type and its existence are settled.

Backlog 16. Before any value exists every edit is safe. Once values exist a
type change would strand them in the wrong typed column -- orphaned, and
nothing reports it -- and a soft delete never reaches the RESTRICT key that
would have refused it. Both are refused in the service, where no client can
bypass them. Making a field mandatory is allowed but says how many records
will be refused at their next save.
"""

# ruff: noqa: D103

from datetime import date
from uuid import UUID

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.branches.schemas import BranchCreate
from app.branches.services import BranchWarehouseService
from app.business.api.router import (
    create_category_rule,
    update_attribute_definition,
)
from app.business.models import (
    AttributeDataType,
    AttributeDefinition,
    AttributeEntityType,
)
from app.business.schemas import (
    AttributeDefinitionUpdate,
    AttributeValueInput,
    CategoryAttributeRuleCreate,
)
from app.business.services import BusinessProfileFrameworkService
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import ConflictError
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims
from app.firms.models import Firm

_ACTOR = UUID("00000000-0000-0000-0000-0000000000a1")


def _session() -> Session:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _principal() -> Principal:
    return Principal(
        subject=_ACTOR,
        roles=frozenset(),
        permissions=frozenset({"PLATFORM_VIEW"}),
        claims=TokenClaims(
            sub=str(_ACTOR), type=TokenType.ACCESS, iat=1, exp=4_102_444_800, roles=[]
        ),
    )


def _setup(*, with_value: bool) -> tuple[Session, AttributeDefinition]:
    """Build a firm, a TEXT field on branches, and two branches, one valued."""
    session = _session()
    firm = Firm(
        name="Acme",
        code="ACME",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(firm)
    definition = AttributeDefinition(
        code="FSSAI_LICENCE",
        name="FSSAI licence",
        entity_type=AttributeEntityType.BRANCH.value,
        data_type=AttributeDataType.TEXT.value,
    )
    session.add(definition)
    session.commit()
    service = BranchWarehouseService(session)
    service.create_branch(
        BranchCreate(
            code="HO",
            name="Head Office",
            attributes=(
                [
                    AttributeValueInput(
                        attribute_definition_id=definition.id, value="F-100"
                    )
                ]
                if with_value
                else []
            ),
        ),
        firm_id=firm.id,
        actor_id=_ACTOR,
    )
    service.create_branch(
        BranchCreate(code="NORTH", name="North"), firm_id=firm.id, actor_id=_ACTOR
    )
    return session, definition


def _update(
    definition: AttributeDefinition, **changes: object
) -> AttributeDefinitionUpdate:
    values: dict[str, object] = {
        "code": definition.code,
        "name": definition.name,
        "entity_type": definition.entity_type,
        "data_type": definition.data_type,
    }
    values.update(changes)
    return AttributeDefinitionUpdate.model_validate(values)


def test_a_type_change_is_refused_once_a_value_is_stored() -> None:
    session, definition = _setup(with_value=True)
    service = BusinessProfileFrameworkService(session)

    with pytest.raises(ConflictError, match="1 stored value"):
        service.update_attribute(
            definition.id, _update(definition, data_type="NUMBER"), _ACTOR
        )

    # The label is not the identity, so renaming stays safe.
    renamed = service.update_attribute(
        definition.id, _update(definition, name="Food licence"), _ACTOR
    )
    assert renamed.name == "Food licence"


def test_a_type_change_is_allowed_before_any_value_exists() -> None:
    session, definition = _setup(with_value=False)
    row = BusinessProfileFrameworkService(session).update_attribute(
        definition.id, _update(definition, data_type="NUMBER"), _ACTOR
    )
    assert row.data_type == "NUMBER"


def test_a_field_holding_values_cannot_be_deleted_but_can_be_deactivated() -> None:
    session, definition = _setup(with_value=True)
    service = BusinessProfileFrameworkService(session)

    with pytest.raises(ConflictError, match="Deactivate it instead"):
        service.delete_attribute(definition.id, _ACTOR)

    retired = service.update_attribute(
        definition.id, _update(definition, is_active=False), _ACTOR
    )
    assert retired.is_active is False


def test_a_field_with_no_values_can_be_deleted() -> None:
    session, definition = _setup(with_value=False)
    BusinessProfileFrameworkService(session).delete_attribute(definition.id, _ACTOR)
    assert session.get(AttributeDefinition, definition.id).is_deleted  # type: ignore[union-attr]


def test_making_a_field_mandatory_warns_with_the_records_that_lack_it() -> None:
    session, definition = _setup(with_value=True)

    response = update_attribute_definition(
        definition.id,
        _update(definition, mandatory=True),
        _principal(),
        type("R", (), {"headers": {}})(),  # type: ignore[arg-type]
        session,
    )

    # NORTH has no licence; HO does.
    assert response.data.warning is not None
    assert "up to 1 branch record" in response.data.warning
    assert response.message == response.data.warning

    # Saving it again while already mandatory says nothing new.
    again = update_attribute_definition(
        definition.id,
        _update(definition, mandatory=True),
        _principal(),
        type("R", (), {"headers": {}})(),  # type: ignore[arg-type]
        session,
    )
    assert again.data.warning is None


def test_a_mandatory_category_rule_warns_too() -> None:
    session, definition = _setup(with_value=False)

    response = create_category_rule(
        CategoryAttributeRuleCreate(
            category_code="ANY",
            attribute_definition_id=definition.id,
            is_mandatory=True,
        ),
        _principal(),
        session,
    )

    assert response.data.warning is not None
    assert "up to 2 branch record" in response.data.warning


def test_a_field_on_a_kind_with_no_records_does_not_warn() -> None:
    session = _session()
    definition = AttributeDefinition(
        code="DRUG_SCHEDULE",
        name="Drug schedule",
        entity_type=AttributeEntityType.PRODUCT.value,
        data_type=AttributeDataType.TEXT.value,
        mandatory=True,
    )
    session.add(definition)
    session.commit()
    service = BusinessProfileFrameworkService(session)
    assert service.mandatory_warning(definition) is None
    assert service.attribute_value_count(definition) == 0
