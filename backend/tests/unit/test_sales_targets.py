"""A target, and whether it was met.

The by-salesman and by-territory reports have always answered "how much" and
never "how much against what". These are the cases that decide whether the
missing half is trustworthy:

- achievement is measured over the **target's** period, not the window a
  report asks for, or a firm running monthly and yearly targets sees one of
  them answered against the wrong dates;
- and on the **target's** basis, because a firm measuring what was collected
  and a firm measuring what was invoiced want different numbers out of the
  same documents;
- and an edit changes what it names and nothing else, because the write
  model's defaults used to be applied to every omission (D-TER-8).
"""

import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.branches.models import Branch
from app.common.audit.models.audit_log import AuditLog
from app.core.database.base import Base
from app.core.exceptions import ConflictError, ValidationError
from app.credit_note.models import CreditNote
from app.customers.models import Customer
from app.firms.models import Firm
from app.identity.models import identity as _identity_models  # noqa: F401
from app.sales_invoice.models import SalesInvoice
from app.sales_targets.schemas import (
    SalesTargetBasis,
    SalesTargetPeriod,
    SalesTargetUpdate,
    SalesTargetWrite,
)
from app.sales_targets.services import SalesTargetService

# Fixtures here type their document numbers; see conftest (D-CFG-2).
pytestmark = pytest.mark.typed_document_numbers

APRIL = (date(2026, 4, 1), date(2026, 4, 30))


def _session_factory() -> sessionmaker[Session]:
    """Build an isolated in-memory schema for one test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _firm(session: Session, code: str = "TGT-FIRM") -> Firm:
    """Create an owning firm."""
    row = Firm(
        name=f"Firm {code}",
        code=code,
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(row)
    session.commit()
    return row


def _branch(session: Session, *, firm_id: UUID) -> Branch:
    """Create a branch, which an invoice cannot be written without."""
    row = Branch(
        firm_id=firm_id,
        code="BR-001",
        name="Branch BR-001",
        display_name="Branch BR-001",
        currency_code="INR",
        working_hours={"start": "09:00", "end": "18:00"},
        status="ACTIVE",
    )
    session.add(row)
    session.commit()
    return row


def _customer(session: Session, *, firm_id: UUID) -> Customer:
    """Create somebody to bill."""
    row = Customer(
        firm_id=firm_id,
        code="CUS-001",
        customer_type="RETAIL",
        name="Customer CUS-001",
        display_name="Customer CUS-001",
        currency_code="INR",
        status="ACTIVE",
    )
    session.add(row)
    session.commit()
    return row


def _invoice(
    session: Session,
    *,
    firm_id: UUID,
    customer_id: UUID,
    branch_id: UUID,
    on: date,
    total: str,
    salesman_id: UUID | None = None,
    status: str = "APPROVED",
) -> None:
    """Write one invoice straight to the table.

    The service reads invoices; raising them through the whole sales chain
    would be testing the chain rather than the target.
    """
    session.add(
        SalesInvoice(
            firm_id=firm_id,
            customer_id=customer_id,
            branch_id=branch_id,
            salesman_id=salesman_id,
            invoice_number=f"SI-{on}-{total}-{status}",
            invoice_date=on,
            status=status,
            grand_total=Decimal(total),
        )
    )
    session.commit()


def _target(
    service: SalesTargetService,
    *,
    firm_id: UUID,
    amount: str,
    salesman_id: UUID | None = None,
    basis: SalesTargetBasis = SalesTargetBasis.INVOICED,
    period: tuple[date, date] = APRIL,
) -> None:
    """Set one target, over April unless told otherwise."""
    service.create_target(
        SalesTargetWrite(
            salesman_id=salesman_id,
            period_start=period[0],
            period_end=period[1],
            period_type=SalesTargetPeriod.MONTHLY,
            basis=basis,
            target_amount=Decimal(amount),
        ),
        firm_id=firm_id,
        actor_id=uuid4(),
    )


def test_achievement_counts_what_was_invoiced_in_the_period() -> None:
    """The simplest case, and the one the rest build on."""
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    customer = _customer(session, firm_id=firm.id)
    service = SalesTargetService(session)
    _target(service, firm_id=firm.id, amount="10000")
    _invoice(
        session,
        firm_id=firm.id,
        customer_id=customer.id,
        branch_id=branch.id,
        on=date(2026, 4, 10),
        total="4000",
    )
    _invoice(
        session,
        firm_id=firm.id,
        customer_id=customer.id,
        branch_id=branch.id,
        on=date(2026, 4, 20),
        total="3500",
    )

    [answer] = service.achievement(
        firm_scope=firm.id, from_date=APRIL[0], to_date=APRIL[1]
    )

    assert answer.achieved_amount == Decimal("7500.00")
    assert answer.shortfall_amount == Decimal("2500.00")
    assert answer.achieved_percent == Decimal("75.00")


def test_a_target_is_measured_over_its_own_period_not_the_window() -> None:
    """A target for April is April's achievement, whatever the report asks.

    Measuring over the window instead would answer a monthly target with a
    year of sales, which is the fault that makes a target report worthless.
    """
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    customer = _customer(session, firm_id=firm.id)
    service = SalesTargetService(session)
    _target(service, firm_id=firm.id, amount="10000")
    _invoice(
        session,
        firm_id=firm.id,
        customer_id=customer.id,
        branch_id=branch.id,
        on=date(2026, 4, 10),
        total="4000",
    )
    # Outside the target's month, inside the report's window.
    _invoice(
        session,
        firm_id=firm.id,
        customer_id=customer.id,
        branch_id=branch.id,
        on=date(2026, 6, 10),
        total="9000",
    )

    [answer] = service.achievement(
        firm_scope=firm.id, from_date=APRIL[0], to_date=date(2026, 12, 31)
    )

    assert answer.achieved_amount == Decimal("4000.00")


def test_a_draft_invoice_is_not_a_sale() -> None:
    """Nor is a cancelled one. Only what was approved counts."""
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    customer = _customer(session, firm_id=firm.id)
    service = SalesTargetService(session)
    _target(service, firm_id=firm.id, amount="10000")
    for status in ("DRAFT", "CANCELLED"):
        _invoice(
            session,
            firm_id=firm.id,
            customer_id=customer.id,
            branch_id=branch.id,
            on=date(2026, 4, 10),
            total="5000",
            status=status,
        )

    [answer] = service.achievement(
        firm_scope=firm.id, from_date=APRIL[0], to_date=APRIL[1]
    )

    assert answer.achieved_amount == Decimal("0.00")


def test_a_target_naming_a_salesman_counts_only_their_sales() -> None:
    """Attribution is the document's own tag, as commission's is."""
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    customer = _customer(session, firm_id=firm.id)
    theirs = uuid4()
    service = SalesTargetService(session)
    _target(service, firm_id=firm.id, amount="10000", salesman_id=theirs)
    _invoice(
        session,
        firm_id=firm.id,
        customer_id=customer.id,
        branch_id=branch.id,
        on=date(2026, 4, 10),
        total="6000",
        salesman_id=theirs,
    )
    _invoice(
        session,
        firm_id=firm.id,
        customer_id=customer.id,
        branch_id=branch.id,
        on=date(2026, 4, 11),
        total="9000",
        salesman_id=uuid4(),
    )

    [answer] = service.achievement(
        firm_scope=firm.id, from_date=APRIL[0], to_date=APRIL[1]
    )

    assert answer.achieved_amount == Decimal("6000.00")


def test_a_target_beaten_reports_no_shortfall() -> None:
    """A shortfall of a negative amount is a sentence nobody can read."""
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    customer = _customer(session, firm_id=firm.id)
    service = SalesTargetService(session)
    _target(service, firm_id=firm.id, amount="1000")
    _invoice(
        session,
        firm_id=firm.id,
        customer_id=customer.id,
        branch_id=branch.id,
        on=date(2026, 4, 10),
        total="2500",
    )

    [answer] = service.achievement(
        firm_scope=firm.id, from_date=APRIL[0], to_date=APRIL[1]
    )

    assert answer.achieved_amount == Decimal("2500.00")
    assert answer.shortfall_amount == Decimal("0.00")
    assert answer.achieved_percent == Decimal("250.00")


def test_a_collected_target_ignores_what_is_merely_billed() -> None:
    """Two firms want different numbers out of the same documents."""
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    customer = _customer(session, firm_id=firm.id)
    service = SalesTargetService(session)
    _target(
        service,
        firm_id=firm.id,
        amount="10000",
        basis=SalesTargetBasis.COLLECTED,
    )
    _invoice(
        session,
        firm_id=firm.id,
        customer_id=customer.id,
        branch_id=branch.id,
        on=date(2026, 4, 10),
        total="8000",
    )

    [answer] = service.achievement(
        firm_scope=firm.id, from_date=APRIL[0], to_date=APRIL[1]
    )

    assert answer.basis == "COLLECTED"
    # Billed but not paid, so a collected target counts none of it.
    assert answer.achieved_amount == Decimal("0.00")


def test_a_second_target_for_one_scope_and_period_is_refused() -> None:
    """Two would leave no answer to whether it was met."""
    session = _session_factory()()
    firm = _firm(session)
    service = SalesTargetService(session)
    _target(service, firm_id=firm.id, amount="10000")

    with pytest.raises(ConflictError):
        _target(service, firm_id=firm.id, amount="20000")


def test_one_firm_s_targets_never_read_another_firm_s_sales() -> None:
    """Firm isolation, which the review checklist asks of every module."""
    session = _session_factory()()
    mine = _firm(session)
    theirs = _firm(session, code="OTH-FIRM")
    branch = _branch(session, firm_id=theirs.id)
    customer = _customer(session, firm_id=theirs.id)
    service = SalesTargetService(session)
    _target(service, firm_id=mine.id, amount="10000")
    _invoice(
        session,
        firm_id=theirs.id,
        customer_id=customer.id,
        branch_id=branch.id,
        on=date(2026, 4, 10),
        total="9000",
    )

    [answer] = service.achievement(
        firm_scope=mine.id, from_date=APRIL[0], to_date=APRIL[1]
    )

    assert answer.achieved_amount == Decimal("0.00")


def test_a_credit_note_takes_the_sale_off_the_target() -> None:
    """D-TER-3: a bill credited in full still met its target.

    9,000 billed against a 10,000 target, then 2,000 credited back: the
    achievement is 7,000. The credit note is written to the table with what
    `credited_against` reads, which is the one derivation of what a bill has
    had taken off it.
    """
    session = _session_factory()()
    firm = _firm(session)
    branch = _branch(session, firm_id=firm.id)
    customer = _customer(session, firm_id=firm.id)
    service = SalesTargetService(session)
    _target(service, firm_id=firm.id, amount="10000")
    _invoice(
        session,
        firm_id=firm.id,
        customer_id=customer.id,
        branch_id=branch.id,
        on=date(2026, 4, 10),
        total="9000",
    )
    invoice = session.scalars(select(SalesInvoice)).one()
    session.add(
        CreditNote(
            firm_id=firm.id,
            customer_id=customer.id,
            branch_id=branch.id,
            sales_invoice_id=invoice.id,
            credit_note_number="CN-1",
            credit_note_date=date(2026, 5, 3),
            status="APPROVED",
            taxable_amount=Decimal("2000"),
            tax_amount=Decimal("0"),
            total_amount=Decimal("2000"),
        )
    )
    session.commit()

    [answer] = service.achievement(
        firm_scope=firm.id, from_date=APRIL[0], to_date=APRIL[1]
    )

    assert answer.achieved_amount == Decimal("7000.00")
    assert answer.shortfall_amount == Decimal("3000.00")


def test_a_target_overlapping_another_on_the_same_basis_is_refused() -> None:
    """D-TER-2: the guard compared start dates, so one from the 2nd slipped in.

    Two targets over the same days on the same basis count the same sales
    twice, and the bonus is then judged on the total. Any overlap is refused
    -- a later start, an earlier start that runs into April, a period that
    swallows it whole.
    """
    session = _session_factory()()
    firm = _firm(session)
    service = SalesTargetService(session)
    _target(service, firm_id=firm.id, amount="10000")

    with pytest.raises(ConflictError):
        _target(
            service,
            firm_id=firm.id,
            amount="1000",
            period=(date(2026, 4, 2), date(2026, 6, 30)),
        )
    with pytest.raises(ConflictError):
        _target(
            service,
            firm_id=firm.id,
            amount="1000",
            period=(date(2026, 3, 1), date(2026, 4, 1)),
        )
    with pytest.raises(ConflictError):
        _target(
            service,
            firm_id=firm.id,
            amount="1000",
            period=(date(2026, 1, 1), date(2026, 12, 31)),
        )
    # The day after it ends is free, and so is the other basis over the
    # same days: what was invoiced and what was collected are different
    # numbers.
    _target(
        service,
        firm_id=firm.id,
        amount="1000",
        period=(date(2026, 5, 1), date(2026, 5, 31)),
    )
    _target(service, firm_id=firm.id, amount="1000", basis=SalesTargetBasis.COLLECTED)
    assert len(service.list_targets(firm_scope=firm.id, page=1, page_size=10)[0]) == 3


def test_an_edit_may_overlap_the_target_it_is_editing() -> None:
    """A row is not in conflict with itself."""
    session = _session_factory()()
    firm = _firm(session)
    service = SalesTargetService(session)
    _target(service, firm_id=firm.id, amount="10000")
    [row] = service.list_targets(firm_scope=firm.id, page=1, page_size=10)[0]

    service.update_target(
        row.id,
        SalesTargetUpdate(
            period_start=date(2026, 4, 1),
            period_end=date(2026, 6, 30),
            target_amount=Decimal("30000"),
        ),
        firm_scope=firm.id,
        actor_id=uuid4(),
    )

    assert row.period_end == date(2026, 6, 30)


def _persons_target(
    session: Session, *, firm_id: UUID, salesman_id: UUID
) -> tuple[SalesTargetService, UUID]:
    """Set a collected target for one person, with notes, and return its id."""
    service = SalesTargetService(session)
    row = service.create_target(
        SalesTargetWrite(
            salesman_id=salesman_id,
            period_start=APRIL[0],
            period_end=APRIL[1],
            period_type=SalesTargetPeriod.MONTHLY,
            basis=SalesTargetBasis.COLLECTED,
            target_amount=Decimal("10000"),
            notes="Includes the trade fair",
        ),
        firm_id=firm_id,
        actor_id=uuid4(),
    )
    return service, row.id


def test_an_edit_naming_only_the_dates_and_amount_keeps_the_rest() -> None:
    """D-TER-8: a PUT of the dates and amount made it the firm's target.

    The write model's defaults -- ``None``, ``None``, MONTHLY, INVOICED,
    ACTIVE -- were applied to every field the body left out, so the person
    was cleared, the basis flipped to INVOICED and the notes went. Absent
    means leave alone. The audit row records the before and after of every
    column that moved, and only those.
    """
    session = _session_factory()()
    firm = _firm(session)
    theirs = uuid4()
    service, target_id = _persons_target(session, firm_id=firm.id, salesman_id=theirs)

    row = service.update_target(
        target_id,
        SalesTargetUpdate(
            period_start=APRIL[0],
            period_end=date(2026, 6, 30),
            target_amount=Decimal("30000"),
        ),
        firm_scope=firm.id,
        actor_id=uuid4(),
    )

    assert row.salesman_id == theirs
    assert row.basis == "COLLECTED"
    assert row.notes == "Includes the trade fair"
    assert row.status == "ACTIVE"
    assert row.period_end == date(2026, 6, 30)
    assert row.target_amount == Decimal("30000")
    [achievement] = service.achievement(
        firm_scope=firm.id, from_date=APRIL[0], to_date=APRIL[1]
    )
    assert achievement.salesman_id == theirs
    audit = session.scalars(
        select(AuditLog).where(AuditLog.action == "sales_target.updated")
    ).one()
    assert audit.before_data is not None and audit.after_data is not None
    assert set(audit.before_data) >= {"period_end", "target_amount"}
    assert "salesman_id" not in audit.after_data
    assert audit.before_data["period_end"] == "2026-04-30"
    assert audit.after_data["period_end"] == "2026-06-30"
    assert audit.after_data["target_amount"] == "30000"


def test_an_explicit_null_still_clears_the_person() -> None:
    """Absent and null are different answers; null is the instruction."""
    session = _session_factory()()
    firm = _firm(session)
    service, target_id = _persons_target(session, firm_id=firm.id, salesman_id=uuid4())

    row = service.update_target(
        target_id,
        SalesTargetUpdate(salesman_id=None, notes=None),
        firm_scope=firm.id,
        actor_id=uuid4(),
    )

    assert row.salesman_id is None
    assert row.notes is None
    assert row.basis == "COLLECTED"
    audit = session.scalars(
        select(AuditLog).where(AuditLog.action == "sales_target.updated")
    ).one()
    assert audit.after_data == {"salesman_id": None, "notes": None}


def test_a_column_a_target_cannot_do_without_is_not_cleared_by_null() -> None:
    """A target with no period, basis or amount is not a target."""
    session = _session_factory()()
    firm = _firm(session)
    service, target_id = _persons_target(session, firm_id=firm.id, salesman_id=uuid4())

    with pytest.raises(ValidationError):
        service.update_target(
            target_id,
            SalesTargetUpdate(basis=None, target_amount=None),
            firm_scope=firm.id,
            actor_id=uuid4(),
        )
    with pytest.raises(ValidationError):
        # The merged period, not the body's own: only the end moved, and it
        # now ends before the row's start.
        service.update_target(
            target_id,
            SalesTargetUpdate(period_end=date(2026, 3, 15)),
            firm_scope=firm.id,
            actor_id=uuid4(),
        )


def test_the_overlap_check_reads_the_merged_row_not_the_body() -> None:
    """A body naming only the dates still belongs to the person it edits.

    Their May target moved back into April would overlap their April one on
    the same basis. Checked against the body alone, the edit reads as a
    firm-wide INVOICED target overlapping nothing, and is let through.
    """
    session = _session_factory()()
    firm = _firm(session)
    theirs = uuid4()
    service, _ = _persons_target(session, firm_id=firm.id, salesman_id=theirs)
    may = service.create_target(
        SalesTargetWrite(
            salesman_id=theirs,
            period_start=date(2026, 5, 1),
            period_end=date(2026, 5, 31),
            basis=SalesTargetBasis.COLLECTED,
            target_amount=Decimal("5000"),
        ),
        firm_id=firm.id,
        actor_id=uuid4(),
    )

    with pytest.raises(ConflictError):
        service.update_target(
            may.id,
            SalesTargetUpdate(period_start=date(2026, 4, 15)),
            firm_scope=firm.id,
            actor_id=uuid4(),
        )


def test_an_edit_that_changes_nothing_writes_nothing() -> None:
    """A save that changes nothing does not move the counter or the trail."""
    session = _session_factory()()
    firm = _firm(session)
    service, target_id = _persons_target(session, firm_id=firm.id, salesman_id=uuid4())
    before = service.get_target(target_id, firm_scope=firm.id).version

    row = service.update_target(
        target_id,
        SalesTargetUpdate(target_amount=Decimal("10000")),
        firm_scope=firm.id,
        actor_id=uuid4(),
    )

    assert row.version == before
    assert (
        session.scalars(
            select(AuditLog).where(AuditLog.action == "sales_target.updated")
        ).first()
        is None
    )


_EDITOR = (
    Path(__file__).resolve().parents[3]
    / "desktop"
    / "lib"
    / "ui"
    / "commission"
    / "sales_target_page.dart"
)


@pytest.mark.skipif(not _EDITOR.exists(), reason="desktop tree not present")
def test_every_key_the_desktop_editor_sends_is_one_the_update_accepts() -> None:
    """The contract from the client's side, as the preference test asks it.

    The schema forbids unknown fields, so one stray key would refuse every
    save; and the keys the editor leaves out are the ones D-TER-8 was about,
    so the update model must treat their absence as leave-alone.
    """
    source = _EDITOR.read_text(encoding="utf-8")
    bodies = re.findall(r"final Json body = <String, dynamic>\{(.*?)\};", source, re.S)
    assert bodies, "no save body found in the desktop editor -- regex drifted?"
    sent = {key for body in bodies for key in re.findall(r"'([a-z_]+)'\s*:", body)}
    assert sent, "the editor's save body names no keys -- regex drifted?"

    unknown = sorted(sent - set(SalesTargetUpdate.model_fields))
    assert not unknown, "the desktop sends keys the update refuses: " + ", ".join(
        unknown
    )
    left_alone = set(SalesTargetUpdate.model_fields) - sent
    assert {"salesman_id", "territory_id", "notes"} <= left_alone
    for field in left_alone:
        assert SalesTargetUpdate.model_fields[field].default is None
