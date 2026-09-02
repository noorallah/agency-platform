"""A target, and whether it was met.

The by-salesman and by-territory reports have always answered "how much" and
never "how much against what". These are the cases that decide whether the
missing half is trustworthy:

- achievement is measured over the **target's** period, not the window a
  report asks for, or a firm running monthly and yearly targets sees one of
  them answered against the wrong dates;
- and on the **target's** basis, because a firm measuring what was collected
  and a firm measuring what was invoiced want different numbers out of the
  same documents.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.branches.models import Branch
from app.core.database.base import Base
from app.core.exceptions import ConflictError
from app.customers.models import Customer
from app.firms.models import Firm
from app.identity.models import identity as _identity_models  # noqa: F401
from app.sales_invoice.models import SalesInvoice
from app.sales_targets.schemas import (
    SalesTargetBasis,
    SalesTargetPeriod,
    SalesTargetWrite,
)
from app.sales_targets.services import SalesTargetService

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
) -> None:
    """Set one target over April."""
    service.create_target(
        SalesTargetWrite(
            salesman_id=salesman_id,
            period_start=APRIL[0],
            period_end=APRIL[1],
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
