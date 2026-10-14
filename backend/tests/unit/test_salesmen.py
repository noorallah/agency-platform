"""The firm's own salesman list (P2, salesman list design, build steps 1-2).

Reading the list is open to any member of the firm, because whoever makes a
bill fills its salesman box; changing it needs ``SALESMAN_MANAGE``. A name is
unique in the firm whatever its case, a user is tied to one entry at most and
must be a member, an update leaves alone what it does not send, and an entry a
document names cannot be deleted.
"""

# ruff: noqa: D103

import importlib.util
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from uuid import UUID, uuid4

import pytest
from fastapi import Response
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.branches.models import Branch
from app.common.audit.models import AuditLog
from app.common.report_names import salesman_names
from app.common.scope import (
    ResolvedFirmScope,
    optional_firm_scope,
    required_firm_scope,
)
from app.core.database.base import Base
from app.core.enums import TokenType
from app.core.exceptions import (
    AuthorizationError,
    ConflictError,
    ResourceNotFoundError,
    ValidationError,
)
from app.core.security.authorization import Principal, require_permission
from app.core.security.jwt import TokenClaims
from app.customers.models import Customer
from app.firms.models import Firm
from app.identity.models import User, UserFirm
from app.identity.system_seed import ROLE_PERMISSION_CODES
from app.sales.models import SalesTerritoryNode, TerritorySalesmanAssignment
from app.sales_invoice.models import SalesInvoice
from app.salesmen.api.router import (
    SalesmanManageScope,
    create_salesman,
    delete_salesman,
    get_salesman,
    list_salesmen,
    restore_salesman,
    router,
    update_salesman,
)
from app.salesmen.models import Salesman
from app.salesmen.naming import free_name, placeholder_name
from app.salesmen.schemas import SalesmanCreate, SalesmanUpdate
from app.salesmen.services.nameable import active_salesman, nameable_salesman

MANAGE = "SALESMAN_MANAGE"


class _Shop:
    """One firm, a manager who holds the code and a clerk who does not."""

    def __init__(self) -> None:
        """Build the firm on a fresh in-memory store."""
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.session = sessionmaker(bind=engine, expire_on_commit=False)()
        self.firm = Firm(
            name="Salesmen Firm",
            code="SLM",
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
        )
        self.session.add(self.firm)
        self.session.commit()
        self.manager = self.member("manager@example.test", "Asha Manager")
        self.clerk = self.member("clerk@example.test", "Ravi Clerk")

    def member(self, email: str, name: str) -> User:
        """Add a user who is an active member of the firm."""
        user = User(email=email, full_name=name, password_hash="hash")
        self.session.add(user)
        self.session.flush()
        self.session.add(
            UserFirm(user_id=user.id, firm_id=self.firm.id, is_active=True)
        )
        self.session.commit()
        return user

    def scope(self, user: User, permissions: set[str]) -> ResolvedFirmScope:
        """Resolve the firm scope as a request does."""
        principal = _principal(user.id, permissions)
        return required_firm_scope(
            optional_firm_scope(
                principal=principal, db=self.session, x_firm_id=self.firm.id
            )
        )

    @property
    def writer(self) -> ResolvedFirmScope:
        """The manager, holding the code."""
        return self.scope(self.manager, {MANAGE})

    def add(self, name: str, **fields: object) -> UUID:
        """Add an entry through the route and return its id."""
        result = create_salesman(
            SalesmanCreate.model_validate({"name": name, **fields}),
            self.writer,
            Response(),
            db=self.session,
        )
        assert result.data is not None
        return result.data.id


def _principal(user_id: UUID, permissions: set[str]) -> Principal:
    """Build an access-token principal holding exactly ``permissions``."""
    return Principal(
        subject=user_id,
        roles=frozenset(),
        permissions=frozenset(permissions),
        claims=TokenClaims(
            sub=str(user_id),
            type=TokenType.ACCESS,
            iat=1,
            exp=4_102_444_800,
            permissions=sorted(permissions),
        ),
    )


@pytest.fixture
def shop() -> _Shop:
    """Provide a fresh firm."""
    return _Shop()


def _names(shop: _Shop, **query: object) -> list[str]:
    """List the entries a member sees, by name."""
    result = list_salesmen(
        shop.scope(shop.clerk, set()),
        **{"page": 1, "page_size": 50, "search": "", **query},  # type: ignore[arg-type]
        db=shop.session,
    )
    return [row.name for row in result.data]


def test_a_member_lists_searches_and_filters_without_any_code(shop: _Shop) -> None:
    shop.add("Mohan", code="m01", phone="98450 11111")
    shop.add("Phone order", earns_commission=False)
    shop.add("Old hand", is_active=False)

    assert _names(shop) == ["Mohan", "Old hand", "Phone order"]
    assert _names(shop, search="M01") == ["Mohan"]
    assert _names(shop, search="11111") == ["Mohan"]
    assert _names(shop, active=True) == ["Mohan", "Phone order"]
    assert _names(shop, active=False) == ["Old hand"]
    assert _names(shop, sort_direction="desc") == ["Phone order", "Old hand", "Mohan"]


def test_a_member_reads_one_entry_with_its_version_as_etag(shop: _Shop) -> None:
    entry = shop.add("Mohan", code="m01")
    response = Response()

    result = get_salesman(
        entry, shop.scope(shop.clerk, set()), response, db=shop.session
    )

    assert result.data is not None
    assert result.data.code == "M01"
    assert response.headers["ETag"] == f'"{result.data.version}"'


def test_every_change_is_on_the_audit_trail(shop: _Shop) -> None:
    entry = shop.add("Mohan")
    update_salesman(
        entry,
        SalesmanUpdate(phone="1234"),
        shop.writer,
        Response(),
        db=shop.session,
    )
    delete_salesman(entry, shop.writer, db=shop.session)
    restore_salesman(entry, shop.writer, Response(), db=shop.session)

    actions = shop.session.scalars(
        select(AuditLog.action)
        .where(AuditLog.entity_id == entry)
        .order_by(AuditLog.created_at)
    ).all()
    assert sorted(actions) == sorted(
        [
            "salesman.created",
            "salesman.updated",
            "salesman.deleted",
            "salesman.restored",
        ]
    )


def test_a_name_is_unique_whatever_its_case(shop: _Shop) -> None:
    shop.add("Mohan")

    with pytest.raises(ConflictError, match="named mOHAN"):
        shop.add("  mOHAN ")


def test_a_code_is_unique_and_blank_codes_do_not_clash(shop: _Shop) -> None:
    shop.add("Mohan", code="M01")
    shop.add("Ravi", code="  ")
    shop.add("Sita")

    with pytest.raises(ConflictError, match="M01"):
        shop.add("Gopal", code="m01")


def test_one_user_is_one_salesman(shop: _Shop) -> None:
    shop.add("Asha", user_id=str(shop.manager.id))

    with pytest.raises(ConflictError, match="already tied"):
        shop.add("Asha again", user_id=str(shop.manager.id))


def test_a_user_who_is_not_a_member_is_refused(shop: _Shop) -> None:
    stranger = User(email="x@example.test", full_name="Stranger", password_hash="h")
    shop.session.add(stranger)
    shop.session.commit()

    with pytest.raises(ValidationError, match="not an active member"):
        shop.add("Stranger", user_id=str(stranger.id))
    with pytest.raises(ValidationError, match="not an active member"):
        shop.add("Nobody", user_id=str(uuid4()))


def test_an_update_leaves_alone_what_it_does_not_send(shop: _Shop) -> None:
    entry = shop.add("Mohan", code="M01", phone="1234", notes="North beat")

    result = update_salesman(
        entry,
        SalesmanUpdate.model_validate({"phone": None, "is_active": False}),
        shop.writer,
        Response(),
        db=shop.session,
    )

    assert result.data is not None
    assert result.data.name == "Mohan"
    assert result.data.code == "M01"
    assert result.data.notes == "North beat"
    assert result.data.phone is None
    assert result.data.is_active is False
    with pytest.raises(ValidationError, match="name"):
        update_salesman(
            entry,
            SalesmanUpdate.model_validate({"name": None}),
            shop.writer,
            Response(),
            db=shop.session,
        )


def test_a_rename_onto_another_entry_is_refused(shop: _Shop) -> None:
    shop.add("Mohan")
    entry = shop.add("Ravi")

    with pytest.raises(ConflictError, match="MOHAN"):
        update_salesman(
            entry,
            SalesmanUpdate(name="MOHAN"),
            shop.writer,
            Response(),
            db=shop.session,
        )
    # Its own name in another case is not a clash with itself.
    update_salesman(
        entry, SalesmanUpdate(name="RAVI"), shop.writer, Response(), db=shop.session
    )


def test_a_stale_version_is_refused(shop: _Shop) -> None:
    entry = shop.add("Mohan")
    first = update_salesman(
        entry,
        SalesmanUpdate(phone="1"),
        shop.writer,
        Response(),
        expected_version=None,
        db=shop.session,
    )
    assert first.data is not None
    stale = first.data.version - 1

    with pytest.raises(ConflictError, match="changed since"):
        update_salesman(
            entry,
            SalesmanUpdate(phone="2"),
            shop.writer,
            Response(),
            expected_version=stale,
            db=shop.session,
        )
    update_salesman(
        entry,
        SalesmanUpdate(phone="2"),
        shop.writer,
        Response(),
        expected_version=first.data.version,
        db=shop.session,
    )


def _invoice_naming(shop: _Shop, salesman_id: UUID) -> SalesInvoice:
    """Record a sales invoice that names the salesman."""
    branch = Branch(
        firm_id=shop.firm.id,
        code="BR-SLM",
        name="Branch",
        display_name="Branch",
        currency_code="INR",
        working_hours={"start": "09:00", "end": "18:00"},
        status="ACTIVE",
        is_default=True,
    )
    customer = Customer(
        firm_id=shop.firm.id,
        code="CUS-SLM",
        customer_type="BUSINESS",
        name="City Stores",
        display_name="City Stores",
        currency_code="INR",
        status="ACTIVE",
        credit_limit=Decimal("0"),
        opening_balance=Decimal("0"),
    )
    shop.session.add_all([branch, customer])
    shop.session.flush()
    invoice = SalesInvoice(
        firm_id=shop.firm.id,
        customer_id=customer.id,
        branch_id=branch.id,
        invoice_number="SI-1",
        invoice_date=date(2026, 10, 14),
        salesman_id=salesman_id,
    )
    shop.session.add(invoice)
    shop.session.commit()
    return invoice


def test_an_entry_a_sales_invoice_names_cannot_be_deleted(shop: _Shop) -> None:
    entry = shop.add("Mohan")
    invoice = _invoice_naming(shop, entry)

    with pytest.raises(ConflictError, match="sales invoice"):
        delete_salesman(entry, shop.writer, db=shop.session)

    # A deleted invoice no longer holds the entry down.
    invoice.is_deleted = True
    shop.session.commit()
    delete_salesman(entry, shop.writer, db=shop.session)


def test_delete_then_restore(shop: _Shop) -> None:
    entry = shop.add("Mohan")

    delete_salesman(entry, shop.writer, db=shop.session)
    assert _names(shop) == []
    with pytest.raises(ResourceNotFoundError):
        get_salesman(entry, shop.writer, Response(), db=shop.session)
    # The name is free again while the entry is deleted.
    other = shop.add("Mohan")
    with pytest.raises(ConflictError, match="Mohan"):
        restore_salesman(entry, shop.writer, Response(), db=shop.session)

    delete_salesman(other, shop.writer, db=shop.session)
    result = restore_salesman(entry, shop.writer, Response(), db=shop.session)
    assert result.data is not None
    assert _names(shop) == ["Mohan"]
    assert shop.session.get(Salesman, entry) is not None
    with pytest.raises(ResourceNotFoundError):
        restore_salesman(entry, shop.writer, Response(), db=shop.session)


def test_writing_needs_salesman_manage_and_reading_does_not(shop: _Shop) -> None:
    code = SalesmanManageScope.__metadata__[0].dependency.permission_code
    assert code == MANAGE

    def enforced(method: str, path: str) -> str | None:
        """Return the permission code one route asks for, if any."""
        route = next(
            item
            for item in router.routes
            if getattr(item, "path", "") == f"/api/v1/salesmen{path}"
            and method in getattr(item, "methods", ())
        )
        codes = {
            getattr(dependency.call, "permission_code", None)
            for dependency in route.dependant.dependencies  # type: ignore[attr-defined]
        }
        return next((item for item in codes if item), None)

    assert enforced("GET", "") is None
    assert enforced("GET", "/{salesman_id}") is None
    for method, path in (
        ("POST", ""),
        ("PUT", "/{salesman_id}"),
        ("DELETE", "/{salesman_id}"),
        ("POST", "/{salesman_id}/restore"),
    ):
        assert enforced(method, path) == MANAGE

    clerk = _principal(shop.clerk.id, {"SALES_VIEW"})
    with pytest.raises(AuthorizationError):
        require_permission(MANAGE)(clerk)
    assert require_permission(MANAGE)(_principal(shop.manager.id, {MANAGE}))


def test_reading_still_needs_membership(shop: _Shop) -> None:
    outsider = User(email="o@example.test", full_name="Outsider", password_hash="h")
    shop.session.add(outsider)
    shop.session.commit()

    with pytest.raises(AuthorizationError):
        shop.scope(outsider, {MANAGE})


def test_the_firm_administrator_and_sales_manager_hold_the_code() -> None:
    assert MANAGE in ROLE_PERMISSION_CODES["FIRM_ADMIN"]
    assert MANAGE in ROLE_PERMISSION_CODES["SALES_MANAGER"]


def test_a_clashing_name_takes_eight_characters_of_the_id() -> None:
    user = UUID("12345678-0000-0000-0000-000000000000")

    assert placeholder_name(user) == "Salesman 12345678"
    assert free_name("Mohan", user, set()) == "Mohan"
    assert free_name("Mohan", user, {"mohan"}) == "Mohan 12345678"
    assert free_name("Mohan", user, {"mohan", "mohan 12345678"}) is None
    assert len(free_name("x" * 200, user, {"x" * 120}) or "") == 120


# -- step 2: who may be named -------------------------------------------------


def test_an_id_on_no_list_is_refused_by_name(shop: _Shop) -> None:
    outsider = User(email="o@example.test", full_name="Outsider", password_hash="h")
    shop.session.add(outsider)
    shop.session.commit()

    for stranger in (uuid4(), outsider.id):
        with pytest.raises(ValidationError, match="not on this firm's list"):
            nameable_salesman(shop.session, shop.firm.id, stranger)


def test_an_inactive_entry_is_refused_and_an_active_one_answered(shop: _Shop) -> None:
    active = shop.add("Mohan")
    resting = shop.add("Old hand", is_active=False)

    assert nameable_salesman(shop.session, shop.firm.id, active) == active
    with pytest.raises(ValidationError, match="Old hand is an inactive salesman"):
        nameable_salesman(shop.session, shop.firm.id, resting)


def test_an_entry_earning_nothing_is_refused_for_commission(shop: _Shop) -> None:
    phone = shop.add("Phone order", earns_commission=False)

    # A bill may name him...
    assert nameable_salesman(shop.session, shop.firm.id, phone) == phone
    # ...a commission rule, a payout or a target may not.
    with pytest.raises(ValidationError, match="Phone order earns no commission"):
        nameable_salesman(shop.session, shop.firm.id, phone, for_commission=True)


def test_another_firms_entry_is_refused(shop: _Shop) -> None:
    other = Salesman(firm_id=uuid4(), name="Elsewhere")
    shop.session.add(other)
    shop.session.commit()

    with pytest.raises(ValidationError, match="not on this firm's list"):
        nameable_salesman(shop.session, shop.firm.id, other.id)


def test_the_bridge_makes_an_entry_of_the_members_own_id(shop: _Shop) -> None:
    clerk = shop.clerk.id

    assert nameable_salesman(shop.session, shop.firm.id, clerk) == clerk
    entry = shop.session.get(Salesman, clerk)
    assert entry is not None
    assert (entry.firm_id, entry.user_id, entry.name) == (
        shop.firm.id,
        clerk,
        "Ravi Clerk",
    )
    assert entry.earns_commission and entry.is_active
    trail = shop.session.scalars(
        select(AuditLog).where(
            AuditLog.entity_id == clerk, AuditLog.action == "salesman.created"
        )
    ).all()
    assert len(trail) == 1
    # Named again, the entry is found rather than made twice.
    assert nameable_salesman(shop.session, shop.firm.id, clerk) == clerk
    assert len(_names(shop)) == 1


def test_the_bridge_takes_a_new_id_where_another_firm_holds_his(shop: _Shop) -> None:
    clerk = shop.clerk.id
    shop.session.add(
        Salesman(id=clerk, firm_id=uuid4(), name="Ravi Clerk", user_id=clerk)
    )
    shop.session.commit()

    answered = nameable_salesman(shop.session, shop.firm.id, clerk)
    assert answered != clerk
    entry = shop.session.get(Salesman, answered)
    assert entry is not None
    assert (entry.firm_id, entry.user_id) == (shop.firm.id, clerk)
    # The user's id now finds this firm's own entry.
    assert nameable_salesman(shop.session, shop.firm.id, clerk) == answered


def test_a_derived_salesman_skips_one_whose_user_has_left(shop: _Shop) -> None:
    tied = shop.add("Ravi", user_id=shop.clerk.id)
    phone = shop.add("Phone order")
    assert active_salesman(shop.session, shop.firm.id, tied) == tied

    membership = shop.session.scalar(
        select(UserFirm).where(UserFirm.user_id == shop.clerk.id)
    )
    assert membership is not None
    membership.is_active = False
    shop.session.commit()

    assert active_salesman(shop.session, shop.firm.id, tied) is None
    # An entry tied to nobody needs no membership.
    assert active_salesman(shop.session, shop.firm.id, phone) == phone


def test_names_are_read_from_the_list_deleted_entries_included(shop: _Shop) -> None:
    mohan = shop.add("Mohan")
    gone = shop.add("Gone")
    delete_salesman(gone, shop.writer, db=shop.session)

    assert salesman_names(shop.session, [mohan, gone, None, uuid4()]) == {
        mohan: "Mohan",
        gone: "Gone",
    }


def _move_migration() -> ModuleType:
    """Load the migration that moves the columns onto the list."""
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "20261014_0382_salesmen_move.py"
    )
    spec = importlib.util.spec_from_file_location("salesmen_move", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_move_points_each_firms_rows_at_its_own_entry(shop: _Shop) -> None:
    """Two firms in one store name one user; a third id has no entry yet."""
    user, late = uuid4(), uuid4()
    first, second = shop.firm.id, uuid4()
    own = uuid4()
    shop.session.add_all(
        [
            # `0380`: the firm naming him most kept the entry of his id.
            Salesman(id=user, firm_id=first, name="Mohan", user_id=user),
            Salesman(id=own, firm_id=second, name="Mohan", user_id=user),
        ]
    )
    shop.session.flush()
    kept = _invoice_naming(shop, user)
    moved = SalesInvoice(
        firm_id=second,
        customer_id=kept.customer_id,
        branch_id=kept.branch_id,
        invoice_number="SI-2",
        invoice_date=date(2026, 10, 14),
        salesman_id=user,
    )
    written_since = SalesInvoice(
        firm_id=second,
        customer_id=kept.customer_id,
        branch_id=kept.branch_id,
        invoice_number="SI-3",
        invoice_date=date(2026, 10, 14),
        salesman_id=late,
    )
    territory = SalesTerritoryNode(
        firm_id=second,
        hierarchy_level_id=uuid4(),
        code="R1",
        name="Round 1",
        path="R1",
    )
    shop.session.add_all([moved, written_since, territory])
    shop.session.flush()
    assignment = TerritorySalesmanAssignment(
        territory_id=territory.id, salesman_id=user
    )
    shop.session.add(assignment)
    shop.session.commit()

    migration = _move_migration()
    connection = shop.session.connection()
    migration._repoint(connection, inspect(connection))
    # A replay finds nothing to move.
    migration._repoint(connection, inspect(connection))
    shop.session.commit()
    shop.session.expire_all()

    assert shop.session.get(SalesInvoice, kept.id).salesman_id == user  # type: ignore[union-attr]
    assert shop.session.get(SalesInvoice, moved.id).salesman_id == own  # type: ignore[union-attr]
    assert (
        shop.session.get(TerritorySalesmanAssignment, assignment.id).salesman_id  # type: ignore[union-attr]
        == own
    )
    # The id written since `0380` became an entry of its own, of that id.
    late_entry = shop.session.get(Salesman, late)
    assert late_entry is not None
    assert (late_entry.firm_id, late_entry.user_id) == (second, late)
    assert shop.session.get(SalesInvoice, written_since.id).salesman_id == late  # type: ignore[union-attr]
    assert len(shop.session.scalars(select(Salesman)).all()) == 3
