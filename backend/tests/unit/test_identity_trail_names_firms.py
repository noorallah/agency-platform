"""Every identity change reaches the trail of the firm it concerns, saying what changed.

D-IDN-5. Identity rows live in the platform store, and a firm's audit screen
merges in only the platform rows whose `firm_id` is that firm. `user.firms_set`
never carried a firm (1,121 on the platform, **0** on TEST01's screen);
`user.updated`, `.deleted`, `.roles_set` and `role.*` carried the *caller's*
scope -- null for every platform administrator -- whatever firm the person or
role belonged to; `user.restored` and `user.password_reset` carried none; a
clone's copied memberships wrote no row at all. And most held no data:
`user.roles_set`, `role.permissions_set` and `user.deleted` said nothing about
what changed, `user.updated` had a before and no after, `firm.updated` only
the name, code and active flag.

Each test drives the change as a **platform** administrator -- the caller whose
scope is null, which is where every one of these rows went missing -- and then
reads the trail the way a firm's screen does: the platform store, filtered on
the firm.
"""

from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.database.all_models  # noqa: F401
from app.common.audit.models import AuditLog
from app.common.audit.schemas import AuditLogFilters
from app.common.audit.services import AuditLogReader
from app.core.config.settings import Settings
from app.core.database.base import Base
from app.firms.models import Firm
from app.firms.schemas import FirmUpdate
from app.firms.services import FirmService
from app.identity.models import Permission, Role, User, UserFirm
from app.identity.schemas.api import (
    RoleCreate,
    RoleUpdate,
    UserCloneRequest,
    UserCreate,
    UserFirmAssignment,
    UserUpdate,
)
from app.identity.services import IdentityService
from app.identity.system_seed import seed_system_rbac

PASSWORD = "Str0ng-Passw0rd!"
ADMIN = uuid4()


def _service() -> tuple[IdentityService, Session]:
    """Build the service over a seeded in-memory schema."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    seed_system_rbac(session)
    session.commit()
    return IdentityService(session, Settings()), session


def _firm(session: Session, code: str) -> Firm:
    """Create one active firm."""
    firm = Firm(
        code=code,
        name=f"Firm {code}",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
        is_active=True,
        created_by=ADMIN,
        updated_by=ADMIN,
    )
    session.add(firm)
    session.commit()
    return firm


def _person(
    service: IdentityService, session: Session, email: str, *firms: Firm
) -> User:
    """Create one user, a member of each firm given."""
    user = service.create_user(
        UserCreate(email=email, full_name="Asha", password=PASSWORD), actor_id=ADMIN
    )
    for index, firm in enumerate(firms):
        session.add(
            UserFirm(
                user_id=user.id,
                firm_id=firm.id,
                is_primary=index == 0,
                is_active=True,
                created_by=ADMIN,
                updated_by=ADMIN,
            )
        )
    session.commit()
    return user


def _role_id(session: Session, code: str) -> UUID:
    """Return one role's id by code."""
    role = session.scalar(select(Role).where(Role.code == code))
    assert role is not None, code
    return role.id


def _on_screen(session: Session, firm: Firm, action: str) -> list[AuditLog]:
    """Read the rows a firm's merged trail takes from the platform store."""
    rows, _ = AuditLogReader(session).list_events(
        firm_scope=firm.id,
        filters=AuditLogFilters(action=action),
        page=1,
        page_size=50,
    )
    return rows


# --------------------------------------------------------------------------
# Memberships and roles
# --------------------------------------------------------------------------


def test_a_membership_change_reaches_each_firm_it_touched() -> None:
    """One row per firm whose membership moved, with that membership's change."""
    service, session = _service()
    one, two = _firm(session, "F1"), _firm(session, "F2")
    person = _person(service, session, "asha@example.com")

    service.set_user_firms(
        person.id,
        [
            UserFirmAssignment(firm_id=one.id, is_primary=True, is_active=True),
            UserFirmAssignment(firm_id=two.id, is_primary=False, is_active=True),
        ],
        ADMIN,
    )

    for firm, primary in ((one, True), (two, False)):
        rows = _on_screen(session, firm, "user.firms_set")
        assert len(rows) == 1
        assert rows[0].entity_id == person.id
        assert rows[0].before_data == {"member": False}
        assert rows[0].after_data == {
            "member": True,
            "is_active": True,
            "is_primary": primary,
        }

    # Leaving one firm is that firm's row, and only that firm's.
    service.set_user_firms(
        person.id,
        [UserFirmAssignment(firm_id=one.id, is_primary=True, is_active=True)],
        ADMIN,
    )
    assert len(_on_screen(session, one, "user.firms_set")) == 1
    left = _on_screen(session, two, "user.firms_set")
    assert len(left) == 2
    assert {"member": False} in [row.after_data for row in left]


def test_a_global_role_change_reaches_every_firm_the_person_works_in() -> None:
    """A global grant applies in each firm, so each firm's trail shows it."""
    service, session = _service()
    one, two = _firm(session, "F1"), _firm(session, "F2")
    person = _person(service, session, "asha@example.com", one, two)

    service.set_user_roles(person.id, [_role_id(session, "VIEWER")], ADMIN, None)

    for firm in (one, two):
        rows = _on_screen(session, firm, "user.roles_set")
        assert len(rows) == 1
        assert rows[0].before_data == {"tier": "global", "role_codes": []}
        assert rows[0].after_data == {"tier": "global", "role_codes": ["VIEWER"]}


def test_a_firm_role_change_names_its_firm_and_the_codes() -> None:
    """The per-firm writer carries both sides of the role set."""
    service, session = _service()
    firm = _firm(session, "F1")
    person = _person(service, session, "asha@example.com", firm)

    service.set_user_firm_roles(
        person.id, firm.id, [_role_id(session, "CASHIER")], ADMIN
    )

    (row,) = _on_screen(session, firm, "user.firm_roles_set")
    assert row.before_data == {"role_codes": []}
    assert row.after_data == {"role_codes": ["CASHIER"]}


def test_a_save_that_changes_nothing_writes_nothing() -> None:
    """A re-save is not an event, and must not bury the ones that are."""
    service, session = _service()
    firm = _firm(session, "F1")
    person = _person(service, session, "asha@example.com", firm)
    service.set_user_roles(person.id, [_role_id(session, "VIEWER")], ADMIN, None)

    service.set_user_roles(person.id, [_role_id(session, "VIEWER")], ADMIN, None)
    service.update_user(person.id, UserUpdate(full_name="Asha"), ADMIN, None)

    assert len(_on_screen(session, firm, "user.roles_set")) == 1
    assert _on_screen(session, firm, "user.updated") == []


# --------------------------------------------------------------------------
# The person
# --------------------------------------------------------------------------


def test_a_platform_edit_of_a_person_reaches_their_firms_with_both_sides() -> None:
    """`user.updated` had a before and no after, and no firm."""
    service, session = _service()
    one, two = _firm(session, "F1"), _firm(session, "F2")
    person = _person(service, session, "asha@example.com", one, two)

    service.update_user(
        person.id, UserUpdate(full_name="Asha Rao", is_active=False), ADMIN, None
    )

    for firm in (one, two):
        (row,) = _on_screen(session, firm, "user.updated")
        assert row.before_data == {"full_name": "Asha", "is_active": True}
        assert row.after_data == {"full_name": "Asha Rao", "is_active": False}


def test_delete_restore_and_reset_reach_the_persons_firm() -> None:
    """Three actions that named no firm, or only the caller's."""
    service, session = _service()
    firm = _firm(session, "F1")
    person = _person(service, session, "asha@example.com", firm)

    service.reset_password(person.id, "An0ther-Passw0rd!", ADMIN)
    service.delete_user(person.id, ADMIN, None)
    service.restore_user(person.id, ADMIN)

    (reset,) = _on_screen(session, firm, "user.password_reset")
    assert reset.after_data == {"force_password_change": True, "lock_cleared": False}
    (deleted,) = _on_screen(session, firm, "user.deleted")
    assert deleted.before_data is not None
    assert deleted.before_data["email"] == "asha@example.com"
    assert deleted.after_data == {"is_deleted": True}
    (restored,) = _on_screen(session, firm, "user.restored")
    assert restored.after_data == {"email": "asha@example.com", "is_deleted": False}
    # Never the credential, anywhere on the trail.
    for row in session.scalars(select(AuditLog)):
        assert "password_hash" not in (row.after_data or {})
        assert "password_hash" not in (row.before_data or {})


def test_a_platform_clone_reaches_every_firm_the_clone_joins() -> None:
    """The copied memberships wrote no row; now each firm sees the clone."""
    service, session = _service()
    one, two = _firm(session, "F1"), _firm(session, "F2")
    source = _person(service, session, "asha@example.com", one, two)

    clone = service.clone_user(
        source.id,
        UserCloneRequest(email="new@example.com", full_name="New", password=PASSWORD),
        ADMIN,
        None,
    )

    for firm in (one, two):
        (row,) = _on_screen(session, firm, "user.cloned")
        assert row.entity_id == clone.id
        assert row.after_data is not None
        assert row.after_data["source_user_id"] == str(source.id)
        assert sorted(row.after_data["firm_ids"]) == sorted([str(one.id), str(two.id)])


# --------------------------------------------------------------------------
# Roles and the firm itself
# --------------------------------------------------------------------------


def test_a_firms_own_role_is_on_that_firms_trail_whoever_changes_it() -> None:
    """Five of six `role.deleted` for TEST01's roles named no firm."""
    service, session = _service()
    firm = _firm(session, "F1")
    role = service.create_role(
        RoleCreate(code="kitchen.staff", name="Kitchen Staff"), ADMIN, firm.id
    )
    view = session.scalar(select(Permission).where(Permission.code == "SALES_VIEW"))
    assert view is not None

    # A platform administrator -- scope None -- edits and retires it.
    service.update_role(role.id, RoleUpdate(name="Kitchen"), ADMIN, None)
    service.set_role_permissions(role.id, [view.id], ADMIN, None)
    service.delete_role(role.id, ADMIN, None)

    (updated,) = _on_screen(session, firm, "role.updated")
    assert updated.before_data == {"name": "Kitchen Staff"}
    assert updated.after_data == {"name": "Kitchen"}
    (granted,) = _on_screen(session, firm, "role.permissions_set")
    assert granted.before_data == {"role_code": "kitchen.staff", "permissions": []}
    assert granted.after_data == {
        "role_code": "kitchen.staff",
        "permissions": ["SALES_VIEW"],
    }
    (deleted,) = _on_screen(session, firm, "role.deleted")
    assert deleted.after_data == {"is_deleted": True}
    assert len(_on_screen(session, firm, "role.created")) == 1


def test_a_firm_edit_records_every_field_that_moved() -> None:
    """`firm.updated` recorded only the name, code and active flag."""
    _, session = _service()
    service = FirmService(session)
    firm = _firm(session, "F1")

    service.update(
        firm.id,
        FirmUpdate(
            name=firm.name,
            code=firm.code,
            country="IN",
            currency_code="INR",
            financial_year_start=date(2026, 4, 1),
            gst_number="29ABCDE1234F1Z5",
        ),
        ADMIN,
    )

    (row,) = _on_screen(session, firm, "firm.updated")
    assert row.after_data is not None
    assert row.after_data["gst_number"] == "29ABCDE1234F1Z5"
    assert row.before_data is not None
    assert row.before_data["gst_number"] is None
    assert "name" not in row.after_data
