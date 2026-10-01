"""A customer's account manager (backlog 67 row 2).

``customers.salesman_id`` names the firm member who looks after the customer.
It must be an active member when it is set, it comes in from the customer
file by email or name, and a sales document raised for the customer with no
salesman of its own takes it -- ahead of the territory's salesperson, but
only when the manager is still here and covers the document's territory.
What the caller names still wins.
"""

from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.common.file_import import ImportReport
from app.core.database.base import Base
from app.core.exceptions import ValidationError
from app.customers.models import Customer
from app.customers.schemas import CustomerCreate, CustomerUpdate
from app.customers.services import CustomerService
from app.customers.services.customer_import import CustomerFileImporter
from app.firms.models import Firm
from app.identity.models import User, UserFirm
from app.sales.schemas import (
    TerritoryAssignCustomersRequest,
    TerritoryAssignSalesmenRequest,
    TerritoryCreate,
)
from app.sales.schemas.territory import (
    RouteProfileInput,
    SalesmanAssignmentInput,
    TerritoryCustomerAssignmentInput,
    VisitFrequency,
)
from app.sales.services import SalesTerritoryService
from app.sales.services.scope_resolution import resolve_sales_scope


@pytest.fixture
def session() -> Session:
    """Return a session on a fresh in-memory schema."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)()


def _firm(session: Session) -> Firm:
    """Add one firm."""
    firm = Firm(
        name="Manager Firm",
        code="MGR01",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
    )
    session.add(firm)
    session.commit()
    return firm


def _member(
    session: Session,
    firm_id: UUID,
    email: str,
    name: str = "Rep",
    *,
    active: bool = True,
) -> UUID:
    """Add a user and their membership of the firm."""
    user = User(email=email, full_name=name, password_hash="hash")
    session.add(user)
    session.flush()
    session.add(UserFirm(user_id=user.id, firm_id=firm_id, is_active=active))
    session.commit()
    return user.id


def _payload(code: str = "SHOP-1", **extra: object) -> dict[str, object]:
    """Return the fields a minimal customer write needs."""
    return {
        "code": code,
        "customer_type": "BUSINESS",
        "name": f"Shop {code}",
        "currency_code": "INR",
        **extra,
    }


def _create(session: Session, firm_id: UUID, **extra: object) -> Customer:
    """Create a customer through the service."""
    return CustomerService(session).create(
        CustomerCreate.model_validate(_payload(**extra)),
        firm_id=firm_id,
        actor_id=uuid4(),
    )


def _route(
    service: SalesTerritoryService, firm_id: UUID, actor: UUID, code: str
) -> UUID:
    """Create one round."""
    hierarchy = service.get_hierarchy(firm_scope=firm_id, actor_id=actor)
    return service.create_territory(
        TerritoryCreate(
            code=code,
            name=code,
            hierarchy_level_id=hierarchy.levels[0].id,
            route_profile=RouteProfileInput(visit_frequency=VisitFrequency.WEEKLY),
        ),
        firm_scope=firm_id,
        actor_id=actor,
    ).id


def _on_round(
    session: Session,
    firm_id: UUID,
    customer_id: UUID,
    salesmen: list[UUID],
) -> UUID:
    """Put the customer on a round its listed salesmen cover."""
    actor = uuid4()
    service = SalesTerritoryService(session)
    route = _route(service, firm_id, actor, "RT01")
    service.set_customers(
        route,
        TerritoryAssignCustomersRequest(
            entries=[
                TerritoryCustomerAssignmentInput(
                    customer_id=customer_id, is_primary=True
                )
            ]
        ),
        firm_scope=firm_id,
        actor_id=actor,
    )
    service.set_salesmen(
        route,
        TerritoryAssignSalesmenRequest(
            assignments=[
                SalesmanAssignmentInput(user_id=user, is_primary=index == 0)
                for index, user in enumerate(salesmen)
            ]
        ),
        firm_scope=firm_id,
        actor_id=actor,
    )
    return route


def test_an_account_manager_must_be_a_member(session: Session) -> None:
    """A stranger, or a member who has left, is refused by name."""
    firm = _firm(session)
    gone = _member(session, firm.id, "gone@example.local", active=False)

    with pytest.raises(ValidationError, match="active member of this firm"):
        _create(session, firm.id, salesman_id=uuid4())
    with pytest.raises(ValidationError, match="active member of this firm"):
        _create(session, firm.id, code="SHOP-2", salesman_id=gone)


def test_a_departed_manager_does_not_block_an_unrelated_edit(
    session: Session,
) -> None:
    """Resending the stored manager is not a change, so it is not re-judged."""
    firm = _firm(session)
    rep = _member(session, firm.id, "rep@example.local")
    customer = _create(session, firm.id, salesman_id=rep)
    assert customer.salesman_id == rep
    membership = session.query(UserFirm).filter_by(user_id=rep).one()
    membership.is_active = False
    session.commit()

    service = CustomerService(session)
    service.update(
        customer.id,
        CustomerUpdate.model_validate(_payload(salesman_id=rep, notes="moved shop")),
        firm_scope=firm.id,
        actor_id=uuid4(),
    )
    assert customer.notes == "moved shop"
    assert customer.salesman_id == rep

    # An update that does not mention it leaves it alone; null clears it.
    service.update(
        customer.id,
        CustomerUpdate.model_validate(
            {
                "code": "SHOP-1",
                "customer_type": "BUSINESS",
                "name": "Shop SHOP-1",
                "currency_code": "INR",
                "salesman_id": None,
            }
        ),
        firm_scope=firm.id,
        actor_id=uuid4(),
    )
    assert customer.salesman_id is None


def test_a_blank_document_takes_the_account_manager(session: Session) -> None:
    """With no territory, the manager is the salesman."""
    firm = _firm(session)
    rep = _member(session, firm.id, "rep@example.local")
    customer = _create(session, firm.id, salesman_id=rep)

    scope = resolve_sales_scope(session, firm_id=firm.id, customer_id=customer.id)

    assert scope.salesman_id == rep


def test_the_manager_comes_before_the_rounds_salesperson(session: Session) -> None:
    """Named for this customer beats covering the area -- if they cover it."""
    firm = _firm(session)
    round_rep = _member(session, firm.id, "round@example.local")
    manager = _member(session, firm.id, "manager@example.local")
    customer = _create(session, firm.id, salesman_id=manager)
    _on_round(session, firm.id, customer.id, [round_rep, manager])

    scope = resolve_sales_scope(session, firm_id=firm.id, customer_id=customer.id)

    assert scope.salesman_id == manager


def test_a_manager_off_the_round_falls_back_to_its_salesperson(
    session: Session,
) -> None:
    """The same name typed on the document would be refused, so it is skipped."""
    firm = _firm(session)
    round_rep = _member(session, firm.id, "round@example.local")
    manager = _member(session, firm.id, "manager@example.local")
    customer = _create(session, firm.id, salesman_id=manager)
    _on_round(session, firm.id, customer.id, [round_rep])

    scope = resolve_sales_scope(session, firm_id=firm.id, customer_id=customer.id)

    assert scope.salesman_id == round_rep


def test_a_departed_manager_is_skipped(session: Session) -> None:
    """Someone who has left stays on the record but names no new document."""
    firm = _firm(session)
    manager = _member(session, firm.id, "manager@example.local")
    customer = _create(session, firm.id, salesman_id=manager)
    session.query(UserFirm).filter_by(user_id=manager).one().is_active = False
    session.commit()

    scope = resolve_sales_scope(session, firm_id=firm.id, customer_id=customer.id)

    assert scope.salesman_id is None


def test_the_documents_own_salesman_wins(session: Session) -> None:
    """What the caller names is validated and kept, never replaced."""
    firm = _firm(session)
    manager = _member(session, firm.id, "manager@example.local")
    other = _member(session, firm.id, "other@example.local")
    customer = _create(session, firm.id, salesman_id=manager)

    scope = resolve_sales_scope(
        session, firm_id=firm.id, customer_id=customer.id, salesman_id=other
    )

    assert scope.salesman_id == other


def _import(
    session: Session, firm_id: UUID, rows: str, *, apply: bool
) -> ImportReport[Customer]:
    """Run a customer file through the importer."""
    return CustomerFileImporter(
        session, CustomerService(session), may_manage_settings=True
    ).run(
        ("Code,Name,Type,AccountManager\n" + rows).encode("utf-8"),
        file_format="csv",
        firm_id=firm_id,
        actor_id=uuid4(),
        existing="refuse",
        apply=apply,
    )


def test_the_file_names_the_manager_by_email_or_name(session: Session) -> None:
    """Email first, then a unique full name; anything else is refused."""
    firm = _firm(session)
    asha = _member(session, firm.id, "asha@example.local", "Asha Rao")
    ravi = _member(session, firm.id, "ravi@example.local", "Ravi K")
    _member(session, firm.id, "ravi2@example.local", "Ravi K")

    report = _import(
        session,
        firm.id,
        "S1,One,BUSINESS,asha@example.local\n"
        "S2,Two,BUSINESS,asha rao\n"
        "S3,Three,BUSINESS,Ravi K\n"
        "S4,Four,BUSINESS,nobody@example.local\n"
        "S5,Five,BUSINESS,RAVI@example.local\n",
        apply=False,
    )

    problems = {(issue.code, issue.column) for issue in report.issues}
    assert problems == {("S3", "AccountManager"), ("S4", "AccountManager")}

    report = _import(
        session,
        firm.id,
        "S1,One,BUSINESS,asha@example.local\nS2,Two,BUSINESS,Asha Rao\n"
        "S5,Five,BUSINESS,RAVI@example.local\nS6,Six,BUSINESS,\n",
        apply=True,
    )
    assert not report.issues
    stored = {
        row.code: row.salesman_id
        for row in session.query(Customer).filter_by(firm_id=firm.id)
    }
    assert stored == {"S1": asha, "S2": asha, "S5": ravi, "S6": None}
