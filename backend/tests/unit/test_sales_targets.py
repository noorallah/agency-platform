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
- and a target on a territory covers the node and every live descendant,
  because a document carries the route and a region is its routes (D-TER-12).
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.branches.models import Branch
from app.core.database.base import Base
from app.core.exceptions import ConflictError
from app.credit_note.models import CreditNote
from app.customers.models import Customer
from app.firms.models import Firm
from app.identity.models import identity as _identity_models  # noqa: F401
from app.sales.models import SalesTerritoryNode
from app.sales_invoice.models import SalesInvoice
from app.sales_targets.schemas import (
    SalesTargetBasis,
    SalesTargetPeriod,
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
    territory_id: UUID | None = None,
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
            territory_id=territory_id,
            invoice_number=f"SI-{on}-{total}-{status}-{territory_id or ''}",
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
    territory_id: UUID | None = None,
    basis: SalesTargetBasis = SalesTargetBasis.INVOICED,
    period: tuple[date, date] = APRIL,
) -> None:
    """Set one target, over April unless told otherwise."""
    service.create_target(
        SalesTargetWrite(
            salesman_id=salesman_id,
            territory_id=territory_id,
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
        SalesTargetWrite(
            period_start=date(2026, 4, 1),
            period_end=date(2026, 6, 30),
            target_amount=Decimal("30000"),
        ),
        firm_scope=firm.id,
        actor_id=uuid4(),
    )

    assert row.period_end == date(2026, 6, 30)


def _node(
    session: Session,
    *,
    firm_id: UUID,
    code: str,
    name: str,
    parent: SalesTerritoryNode | None = None,
) -> SalesTerritoryNode:
    """Write one territory node under its parent, with the path the tree keeps."""
    row = SalesTerritoryNode(
        firm_id=firm_id,
        hierarchy_level_id=uuid4(),
        parent_id=parent.id if parent else None,
        code=code,
        name=name,
        path=code if parent is None else f"{parent.path}/{code}",
    )
    session.add(row)
    session.commit()
    return row


def _tree(session: Session, firm_id: UUID) -> dict[str, SalesTerritoryNode]:
    """Build a region over a territory over two routes, and a look-alike sibling.

    The sibling region is coded `T-N2` beside `T-N`, and its route's path
    starts with the first region's: exactly what a `path LIKE 'T-N%'` would
    have swept in. And `T_N` beside them, because `_` is a wildcard to LIKE.
    """
    region = _node(session, firm_id=firm_id, code="T-N", name="North")
    territory = _node(
        session, firm_id=firm_id, code="T-N-CITY", name="North City", parent=region
    )
    route_a = _node(
        session, firm_id=firm_id, code="T-N-CITY-A", name="Route A", parent=territory
    )
    route_b = _node(
        session, firm_id=firm_id, code="T-N-CITY-B", name="Route B", parent=territory
    )
    sibling = _node(session, firm_id=firm_id, code="T-N2", name="North Two")
    route_c = _node(
        session, firm_id=firm_id, code="T-N2-C", name="Route C", parent=sibling
    )
    underscore = _node(session, firm_id=firm_id, code="T_N", name="Underscore")
    return {
        "region": region,
        "territory": territory,
        "route_a": route_a,
        "route_b": route_b,
        "sibling": sibling,
        "route_c": route_c,
        "underscore": underscore,
    }


def _bill_every_route(
    session: Session, *, firm_id: UUID, tree: dict[str, SalesTerritoryNode]
) -> None:
    """Invoice 4,000 on route A, 3,000 on route B, and 9,000 outside the region."""
    branch = _branch(session, firm_id=firm_id)
    customer = _customer(session, firm_id=firm_id)
    for node, total in (
        ("route_a", "4000"),
        ("route_b", "3000"),
        ("route_c", "9000"),
        ("underscore", "9000"),
    ):
        _invoice(
            session,
            firm_id=firm_id,
            customer_id=customer.id,
            branch_id=branch.id,
            on=date(2026, 4, 10),
            total=total,
            territory_id=tree[node].id,
        )


def test_a_target_on_a_region_counts_what_its_routes_sold() -> None:
    """D-TER-12: a 5,000 target on a region read 0.00 with 10,620 on its routes.

    A document carries the route its customer is on, so a target matched on
    that column alone achieved nothing on any level above it. The region is
    its routes: 4,000 on A and 3,000 on B count, and neither the look-alike
    sibling `T-N2` nor `T_N` does. The row is labelled with the territory
    rather than "Whole firm".
    """
    session = _session_factory()()
    firm = _firm(session)
    tree = _tree(session, firm.id)
    _bill_every_route(session, firm_id=firm.id, tree=tree)
    service = SalesTargetService(session)
    _target(service, firm_id=firm.id, amount="5000", territory_id=tree["region"].id)

    [answer] = service.achievement(
        firm_scope=firm.id, from_date=APRIL[0], to_date=APRIL[1]
    )

    assert answer.achieved_amount == Decimal("7000.00")
    assert answer.shortfall_amount == Decimal("0.00")
    assert answer.territory_code == "T-N"
    assert answer.territory_name == "North"
    assert answer.scope_label == "T-N · North"
    assert answer.salesman_name == "T-N · North"
    [row] = service.list_targets(firm_scope=firm.id, page=1, page_size=10)[0]
    listed = service.target_response(row)
    assert listed.scope_label == "T-N · North"
    assert listed.territory_code == "T-N"


def test_a_target_on_a_route_counts_only_its_own_route() -> None:
    """The bottom of the tree has no descendants, so it takes exactly itself."""
    session = _session_factory()()
    firm = _firm(session)
    tree = _tree(session, firm.id)
    _bill_every_route(session, firm_id=firm.id, tree=tree)
    service = SalesTargetService(session)
    _target(service, firm_id=firm.id, amount="5000", territory_id=tree["route_b"].id)

    [answer] = service.achievement(
        firm_scope=firm.id, from_date=APRIL[0], to_date=APRIL[1]
    )

    assert answer.achieved_amount == Decimal("3000.00")


def test_a_person_s_target_on_a_region_takes_only_their_sales_in_it() -> None:
    """Both halves of the scope apply: their sales, on the region's routes."""
    session = _session_factory()()
    firm = _firm(session)
    tree = _tree(session, firm.id)
    branch = _branch(session, firm_id=firm.id)
    customer = _customer(session, firm_id=firm.id)
    theirs = uuid4()
    for node, total, who in (
        ("route_a", "4000", theirs),
        ("route_b", "3000", uuid4()),
        ("route_c", "9000", theirs),
    ):
        _invoice(
            session,
            firm_id=firm.id,
            customer_id=customer.id,
            branch_id=branch.id,
            on=date(2026, 4, 10),
            total=total,
            salesman_id=who,
            territory_id=tree[node].id,
        )
    service = SalesTargetService(session)
    _target(
        service,
        firm_id=firm.id,
        amount="5000",
        salesman_id=theirs,
        territory_id=tree["region"].id,
    )

    [answer] = service.achievement(
        firm_scope=firm.id, from_date=APRIL[0], to_date=APRIL[1]
    )

    assert answer.achieved_amount == Decimal("4000.00")
    assert answer.scope_label.endswith(" · T-N · North")


def test_a_region_target_and_a_route_target_beneath_it_are_different_scopes() -> None:
    """The D-TER-2 overlap rule is not widened by the tree.

    A firm may set the region a number and one of its routes a number over
    the same days on the same basis: they are different questions, and the
    bonus is judged per person rather than by adding territory targets up.
    """
    session = _session_factory()()
    firm = _firm(session)
    tree = _tree(session, firm.id)
    service = SalesTargetService(session)
    _target(service, firm_id=firm.id, amount="5000", territory_id=tree["region"].id)
    _target(service, firm_id=firm.id, amount="2000", territory_id=tree["route_a"].id)

    with pytest.raises(ConflictError):
        _target(service, firm_id=firm.id, amount="1", territory_id=tree["region"].id)
    assert len(service.list_targets(firm_scope=firm.id, page=1, page_size=10)[0]) == 2
