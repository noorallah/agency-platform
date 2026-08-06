"""Document lifecycle framework tests."""

import importlib
from datetime import date
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.document_framework.models import (
    DocumentLifecycleEvent,
    DocumentNumberingRule,
    DocumentStateDefinition,
    DocumentTypeDefinition,
)
from app.document_framework.schemas import (
    DocumentLifecycleEventCreate,
    DocumentNumberingRuleCreate,
    DocumentStateCreate,
    DocumentTypeCreate,
)
from app.document_framework.services import DocumentFrameworkService
from app.firms.models import Firm

importlib.import_module("app.document_framework.models.document_framework")


def _session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _firm(session: Session) -> Firm:
    row = Firm(
        name="Generic Firm",
        code="GEN",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(row)
    session.commit()
    return row


def test_document_framework_supports_configuration_and_timeline() -> None:
    """Ensure document catalogs, numbering, and timeline logging stay generic."""
    session = _session_factory()()
    firm = _firm(session)
    actor_id = uuid4()
    service = DocumentFrameworkService(session)

    document_type = service.create_type(
        firm.id,
        DocumentTypeCreate(code="PURCHASE_ORDER", name="Purchase Order"),
        actor_id,
    )
    state = service.create_state(
        firm.id,
        DocumentStateCreate(
            document_type_id=document_type.id,
            code="DRAFT",
            name="Draft",
            is_default=True,
        ),
        actor_id,
    )
    rule = service.create_numbering_rule(
        firm.id,
        DocumentNumberingRuleCreate(
            document_type_id=document_type.id,
            code="DEFAULT",
            name="Default Numbering",
            prefix="PO",
            include_financial_year=True,
        ),
        actor_id,
    )

    assert (
        session.scalar(
            select(DocumentTypeDefinition).where(
                DocumentTypeDefinition.id == document_type.id
            )
        )
        is not None
    )
    assert (
        session.scalar(
            select(DocumentStateDefinition).where(
                DocumentStateDefinition.id == state.id
            )
        )
        is not None
    )
    assert (
        session.scalar(
            select(DocumentNumberingRule).where(DocumentNumberingRule.id == rule.id)
        )
        is not None
    )

    assert (
        service.preview_number(
            rule.id,
            firm_id=firm.id,
            document_date=date(2026, 1, 1),
            financial_year_label="2026",
        )
        == "PO-2026-000001"
    )

    reserved = service.reserve_number(
        rule.id,
        firm_id=firm.id,
        document_date=date(2026, 1, 1),
        financial_year_label="2026",
        actor_id=actor_id,
    )
    assert reserved == "PO-2026-000001"
    assert session.get(DocumentNumberingRule, rule.id).next_sequence == 2

    event = service.record_event(
        firm.id,
        DocumentLifecycleEventCreate(
            document_type_id=document_type.id,
            source_document_id=uuid4(),
            action="CREATED",
            from_state=None,
            to_state="DRAFT",
            remarks="Created from the generic framework.",
        ),
        actor_id,
    )
    rows, total = service.list_timeline(firm.id, event.source_document_id, 1, 20, True)

    assert total == 1
    assert rows[0].action == "CREATED"
    assert (
        session.scalar(
            select(DocumentLifecycleEvent).where(DocumentLifecycleEvent.id == event.id)
        )
        is not None
    )
