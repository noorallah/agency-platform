"""Document lifecycle framework tests."""

import importlib
from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.document_framework.models import (
    DocumentLifecycleEvent,
    DocumentNumberingRule,
    DocumentStateDefinition,
    DocumentTypeDefinition,
)
from app.document_framework.schemas import (
    DocumentLifecycleEventCreate,
    DocumentNumberingRuleCreate,
    DocumentNumberingRuleUpdate,
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


def test_back_dating_a_document_does_not_renumber_the_current_year() -> None:
    """Each numbering scope keeps its own counter.

    The rule used to carry one ``next_sequence`` and the last scope it had
    seen, resetting to 1 whenever the scope changed. Entering a missed invoice
    dated in the previous financial year -- ordinary accounting -- reset the
    counter, and the next current-year document was then handed a number that
    year had already issued. Document numbers are unique per firm, so that
    second document failed outright and the only way to carry on was to stop
    back-dating.
    """
    session = _session_factory()()
    firm = _firm(session)
    actor_id = uuid4()
    service = DocumentFrameworkService(session)
    document_type = service.create_type(
        firm.id,
        DocumentTypeCreate(code="SALES_INVOICE", name="Sales Invoice"),
        actor_id,
    )
    rule = service.create_numbering_rule(
        firm.id,
        DocumentNumberingRuleCreate(
            document_type_id=document_type.id,
            code="DEFAULT",
            name="Default Numbering",
            prefix="INV",
            include_financial_year=True,
        ),
        actor_id,
    )

    def reserve(label: str, on: date) -> str:
        return service.reserve_number(
            rule.id,
            firm_id=firm.id,
            document_date=on,
            financial_year_label=label,
            actor_id=actor_id,
        )

    # Three invoices in the current year.
    current = [reserve("2026-2027", date(2026, 8, day)) for day in (1, 2, 3)]
    assert current == [
        "INV-2026-2027-000001",
        "INV-2026-2027-000002",
        "INV-2026-2027-000003",
    ]

    # A missed invoice from last year. It starts its own series at one.
    assert reserve("2025-2026", date(2026, 3, 30)) == "INV-2025-2026-000001"

    # Back in the current year, numbering continues where it left off. It used
    # to restart at 000001 and collide with the first invoice above.
    assert reserve("2026-2027", date(2026, 8, 4)) == "INV-2026-2027-000004"

    # And last year continues independently too.
    assert reserve("2025-2026", date(2026, 3, 31)) == "INV-2025-2026-000002"


def test_every_number_a_rule_issues_is_unique() -> None:
    """Interleave two scopes heavily and check nothing repeats."""
    session = _session_factory()()
    firm = _firm(session)
    actor_id = uuid4()
    service = DocumentFrameworkService(session)
    document_type = service.create_type(
        firm.id,
        DocumentTypeCreate(code="DELIVERY_NOTE", name="Delivery Note"),
        actor_id,
    )
    rule = service.create_numbering_rule(
        firm.id,
        DocumentNumberingRuleCreate(
            document_type_id=document_type.id,
            code="DEFAULT",
            name="Default Numbering",
            prefix="DN",
            include_financial_year=True,
        ),
        actor_id,
    )

    issued: list[str] = []
    for index in range(12):
        label = "2026-2027" if index % 2 else "2025-2026"
        on = date(2026, 8, 1) if index % 2 else date(2026, 2, 1)
        issued.append(
            service.reserve_number(
                rule.id,
                firm_id=firm.id,
                document_date=on,
                financial_year_label=label,
                actor_id=actor_id,
            )
        )

    assert len(set(issued)) == len(issued), f"duplicate numbers issued: {issued}"


def test_a_preview_shows_the_number_the_document_would_actually_get() -> None:
    """Found by building the numbering screen and reading its output.

    The label fell through as None when a caller did not name one, so a
    preview read ``PO-2026-000001`` while the document it was previewing would
    be called ``PO-2026-2027-000001``. Showing the wrong number is the one
    thing a preview must not do.
    """
    session = _session_factory()()
    firm = _firm(session)
    actor_id = uuid4()
    service = DocumentFrameworkService(session)
    document_type = service.create_type(
        firm.id,
        DocumentTypeCreate(code="PURCHASE_ORDER", name="Purchase Order"),
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

    # The firm's year starts in April, so a January date is in 2025-2026.
    preview = service.preview_number(
        rule.id, firm_id=firm.id, document_date=date(2026, 1, 1)
    )
    reserved = service.reserve_number(
        rule.id, firm_id=firm.id, document_date=date(2026, 1, 1), actor_id=actor_id
    )

    assert preview == "PO-2025-2026-000001"
    assert reserved == preview


def _numbering_setup() -> tuple[DocumentFrameworkService, UUID, UUID, UUID]:
    """Build a firm with a document type, ready for a numbering rule."""
    session = _session_factory()()
    firm = _firm(session)
    actor_id = uuid4()
    service = DocumentFrameworkService(session)
    document_type = service.create_type(
        firm.id,
        DocumentTypeCreate(code="NUMBERED", name="Numbered"),
        actor_id,
    )
    return service, firm.id, document_type.id, actor_id


def test_a_rule_that_resets_yearly_must_show_the_year() -> None:
    """Otherwise 1 April repeats a number the firm has already issued.

    The scope signature carried the financial year unconditionally, so every
    rule reset each April -- while `include_financial_year` defaults to
    **False**, which makes the colliding shape the one a rule takes when
    nobody thinks about it. `PRB-000001` in March and `PRB-000001` again in
    April, and the per-firm uniqueness key on every document table rejects the
    second one: the firm cannot raise its first document of the new year, and
    nothing on screen says why.

    Refused when the rule is configured, which is the only moment anybody is
    in a position to fix it.
    """
    service, firm_id, type_id, actor_id = _numbering_setup()

    with pytest.raises(ValidationError, match="has to include the year"):
        service.create_numbering_rule(
            firm_id,
            DocumentNumberingRuleCreate(
                document_type_id=type_id,
                code="HIDDEN",
                name="Hides the year",
                prefix="PRB",
                include_financial_year=False,
            ),
            actor_id,
        )


def test_a_format_pattern_is_checked_for_the_placeholder_instead() -> None:
    """A pattern overrides the flags, so the flags cannot answer for it."""
    service, firm_id, type_id, actor_id = _numbering_setup()

    with pytest.raises(ValidationError, match="format pattern"):
        service.create_numbering_rule(
            firm_id,
            DocumentNumberingRuleCreate(
                document_type_id=type_id,
                code="PATTERNED",
                name="Patterned",
                include_financial_year=True,
                format_pattern="{prefix}{separator}{sequence}",
            ),
            actor_id,
        )

    accepted = service.create_numbering_rule(
        firm_id,
        DocumentNumberingRuleCreate(
            document_type_id=type_id,
            code="PATTERNED_OK",
            name="Patterned, with the year",
            prefix="INV",
            include_financial_year=False,
            format_pattern="{prefix}{separator}{financial_year}{separator}{sequence}",
        ),
        actor_id,
    )
    assert accepted.format_pattern is not None


def test_turning_the_reset_off_gives_one_continuous_series() -> None:
    """`auto_reset` was stored, returned, rendered -- and read by nothing.

    Every rule reset every April whatever a firm had configured, which is the
    defect this repo records from the tax review: a flag the engine records
    has to change an outcome. With the reset off there is one series for the
    life of the rule, which is what a firm numbering straight through wants
    and could not previously have had.
    """
    service, firm_id, type_id, actor_id = _numbering_setup()
    rule = service.create_numbering_rule(
        firm_id,
        DocumentNumberingRuleCreate(
            document_type_id=type_id,
            code="CONTINUOUS",
            name="Straight through",
            prefix="SEQ",
            include_financial_year=False,
            auto_reset=False,
        ),
        actor_id,
    )

    def reserve(label: str, on: date) -> str:
        return service.reserve_number(
            rule.id,
            firm_id=firm_id,
            document_date=on,
            financial_year_label=label,
            actor_id=actor_id,
        )

    assert reserve("2025-2026", date(2026, 3, 30)) == "SEQ-000001"
    assert reserve("2025-2026", date(2026, 3, 31)) == "SEQ-000002"
    # Across the year boundary the count carries on rather than restarting.
    assert reserve("2026-2027", date(2026, 4, 1)) == "SEQ-000003"
    assert reserve("2026-2027", date(2026, 4, 2)) == "SEQ-000004"


def test_a_partial_update_is_judged_on_what_the_rule_will_be() -> None:
    """The collision can be assembled from one stored field and one sent one.

    The update is partial, so a caller switching the year off says nothing
    about `auto_reset`. Reading the request alone would let that through and
    leave the rule in exactly the state creation refuses.
    """
    service, firm_id, type_id, actor_id = _numbering_setup()
    rule = service.create_numbering_rule(
        firm_id,
        DocumentNumberingRuleCreate(
            document_type_id=type_id,
            code="EDITED",
            name="Edited",
            prefix="EDT",
            include_financial_year=True,
        ),
        actor_id,
    )

    with pytest.raises(ValidationError, match="has to include the year"):
        service.update_numbering_rule(
            firm_id,
            rule.id,
            DocumentNumberingRuleUpdate(
                document_type_id=type_id,
                code="EDITED",
                name="Edited",
                include_financial_year=False,
            ),
            actor_id,
        )

    # Turning the reset off in the same edit is accepted, because then there
    # is no reset for the year to be missing from.
    service.update_numbering_rule(
        firm_id,
        rule.id,
        DocumentNumberingRuleUpdate(
            document_type_id=type_id,
            code="EDITED",
            name="Edited",
            include_financial_year=False,
            auto_reset=False,
        ),
        actor_id,
    )
