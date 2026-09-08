"""Custom fields reach branches and warehouses.

The same last mile customers and vendors got on 2026-09-08, on the same
day: the write on create, the partial rule on update (absent leaves them
alone, sent replaces them), the wrong-entity refusal, and the response
carrying the stored values through the router's helpers.
"""

# ruff: noqa: D101,D102,D103

from datetime import date
from uuid import UUID

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.branches.api.router import _attributes, _warehouse_response
from app.branches.models import BranchAttributeValue
from app.branches.schemas import (
    BranchCreate,
    BranchUpdate,
    WarehouseCreate,
    WarehouseUpdate,
)
from app.branches.services import BranchWarehouseService
from app.business.models import (
    AttributeDataType,
    AttributeDefinition,
    AttributeEntityType,
)
from app.business.schemas import AttributeValueInput
from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.firms.models import Firm

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
) -> AttributeDefinition:
    row = AttributeDefinition(
        code=code,
        name=code.replace("_", " ").title(),
        entity_type=entity_type.value,
        data_type=data_type.value,
    )
    session.add(row)
    session.commit()
    return row


def test_a_branch_carries_a_custom_field_through_create_update_and_read() -> None:
    session = _session()
    firm = _firm(session)
    fssai = _definition(session, "FSSAI_LICENCE", AttributeEntityType.BRANCH)
    service = BranchWarehouseService(session)

    branch = service.create_branch(
        BranchCreate(
            code="HO",
            name="Head Office",
            attributes=[
                AttributeValueInput(attribute_definition_id=fssai.id, value="F-100")
            ],
        ),
        firm_id=firm.id,
        actor_id=_ACTOR,
    )
    assert [
        v.value_text for v in _attributes(BranchAttributeValue, branch, session)
    ] == ["F-100"]

    # A rename from a form that shows no custom fields keeps them.
    service.update_branch(
        branch.id,
        BranchUpdate(code="HO", name="Head Office (renamed)"),
        firm_scope=firm.id,
        actor_id=_ACTOR,
    )
    assert [
        v.value_text for v in _attributes(BranchAttributeValue, branch, session)
    ] == ["F-100"]

    # An explicit empty list clears them.
    service.update_branch(
        branch.id,
        BranchUpdate(code="HO", name="Head Office", attributes=[]),
        firm_scope=firm.id,
        actor_id=_ACTOR,
    )
    assert _attributes(BranchAttributeValue, branch, session) == []


def test_a_warehouse_carries_a_typed_custom_field_and_refuses_a_branch_one() -> None:
    session = _session()
    firm = _firm(session)
    service = BranchWarehouseService(session)
    branch = service.create_branch(
        BranchCreate(code="HO", name="Head Office"), firm_id=firm.id, actor_id=_ACTOR
    )
    bays = _definition(
        session,
        "DOCK_BAYS",
        AttributeEntityType.WAREHOUSE,
        data_type=AttributeDataType.NUMBER,
    )
    branch_only = _definition(session, "FSSAI_LICENCE", AttributeEntityType.BRANCH)

    warehouse = service.create_warehouse(
        WarehouseCreate(
            branch_id=branch.id,
            code="MAIN",
            name="Main",
            attributes=[AttributeValueInput(attribute_definition_id=bays.id, value=4)],
        ),
        firm_id=firm.id,
        actor_id=_ACTOR,
    )
    response = _warehouse_response(warehouse, session)
    assert response.attributes[0].value_number == 4
    assert response.attributes[0].value_text is None

    with pytest.raises(ValidationError, match="do not apply to this record"):
        service.update_warehouse(
            warehouse.id,
            WarehouseUpdate(
                branch_id=branch.id,
                code="MAIN",
                name="Main",
                attributes=[
                    AttributeValueInput(
                        attribute_definition_id=branch_only.id, value="F-1"
                    )
                ],
            ),
            firm_scope=firm.id,
            actor_id=_ACTOR,
        )
