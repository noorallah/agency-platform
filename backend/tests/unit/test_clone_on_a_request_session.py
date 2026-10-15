"""A firm administrator's clone works on a session that does not autoflush.

D-IDN-14. `_stage_create_user` added the clone's `UserFirm` row and returned
without flushing; `_stage_set_user_roles` then re-read the clone through
`_get_user`, which looks for a membership in the firm. The unit fixtures
autoflush, so the row was there; a request session does not, so every
`POST /users/{id}/clone` by a firm administrator whose source held a role
answered 404 "User not found." and wrote nothing (users and roles round 1).
"""

from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.database.all_models  # noqa: F401
from app.core.config.settings import Settings
from app.core.database.base import Base
from app.firms.models import Firm
from app.identity.models import Role, UserFirm, UserRole
from app.identity.schemas.api import UserCloneRequest, UserCreate
from app.identity.services import IdentityService
from app.identity.system_seed import seed_system_rbac

PASSWORD = "Str0ng-Passw0rd!"
ACTOR = uuid4()


def _service() -> tuple[IdentityService, Session]:
    """Build the service over a seeded schema, on a session shaped like a request's."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)()
    seed_system_rbac(session)
    session.commit()
    return IdentityService(session, Settings()), session


def _role_id(session: Session, code: str) -> UUID:
    """Return one role's id by code."""
    role = session.scalar(select(Role).where(Role.code == code))
    assert role is not None, code
    return role.id


def test_a_firm_administrator_clones_somebody_who_holds_a_role() -> None:
    """The clone is made, a member of the firm, holding the source's role."""
    service, session = _service()
    firm = Firm(
        code="T1",
        name="Firm T1",
        country="IN",
        currency_code="INR",
        financial_year_start=date(2026, 4, 1),
        is_active=True,
        created_by=ACTOR,
        updated_by=ACTOR,
    )
    session.add(firm)
    session.commit()
    source = service.create_user(
        UserCreate(email="source@example.com", full_name="Source", password=PASSWORD),
        actor_id=ACTOR,
        firm_scope=firm.id,
    )
    service.set_user_firm_roles(
        source.id, firm.id, [_role_id(session, "CASHIER")], ACTOR
    )

    clone = service.clone_user(
        source.id,
        UserCloneRequest(
            email="clone@example.com", full_name="New Hire", password=PASSWORD
        ),
        ACTOR,
        firm.id,
    )

    assert session.scalar(
        select(UserFirm.id).where(
            UserFirm.user_id == clone.id, UserFirm.firm_id == firm.id
        )
    )
    held = set(
        session.scalars(
            select(Role.code)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == clone.id, UserRole.is_deleted.is_(False))
        )
    )
    assert held == {"CASHIER"}
