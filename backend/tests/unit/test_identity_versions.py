"""Roles, users and templates publish their version and honour `If-Match`.

D-IDN-15. None of the three published an `ETag` or a `version`, and none
accepted an expected version, so two administrators editing one role both
saved and the last one won. The precondition stays opt-in: sending nothing is
still accepted.
"""

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import Response
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.database.all_models  # noqa: F401
from app.core.config.settings import Settings
from app.core.database.base import Base
from app.core.exceptions import ConflictError
from app.core.security.authorization import Principal
from app.identity.api.router import create_role, get_role, update_role
from app.identity.models import Role
from app.identity.schemas.api import (
    RoleCreate,
    RoleUpdate,
    UserTemplateCreate,
    UserTemplateUpdate,
)
from app.identity.services import IdentityService
from app.identity.system_seed import seed_system_rbac


def _session() -> Session:
    """Build a seeded in-memory schema."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    seed_system_rbac(session)
    session.commit()
    return session


def _principal() -> Principal:
    """Build a platform caller who may manage roles everywhere."""
    return Principal(
        subject=uuid4(),
        roles=frozenset(),
        permissions=frozenset({"ROLE_CREATE", "ROLE_UPDATE", "ROLE_VIEW"}),
        claims=SimpleNamespace(  # type: ignore[arg-type]
            model_extra={"platform_admin": True, "platform_admin_scope": "PLATFORM"}
        ),
        firm_permissions={},
    )


def _role(session: Session, principal: Principal) -> tuple[UUID, Response]:
    """Create one custom role through the route; return its id and response."""
    response = Response()
    created = create_role(
        RoleCreate(code="packer", name="Packer"),
        principal,
        response,
        db=session,
        settings=Settings(),
    )
    assert created.data is not None
    return created.data.id, response


def test_a_role_publishes_its_version_on_the_body_and_as_an_etag() -> None:
    """Create and GET both carry the version a client must echo back."""
    session = _session()
    principal = _principal()
    role_id, created = _role(session, principal)
    assert created.headers["ETag"] == '"1"'

    response = Response()
    fetched = get_role(role_id, principal, response, db=session, settings=Settings())
    assert fetched.data is not None
    assert fetched.data.version == 1
    assert response.headers["ETag"] == '"1"'


def test_a_stale_role_update_is_refused() -> None:
    """The second administrator's save, aimed at version 1, meets a 409."""
    session = _session()
    principal = _principal()
    role_id, _ = _role(session, principal)

    first = Response()
    update_role(
        role_id,
        RoleUpdate(name="Packer (day)"),
        principal,
        first,
        expected_version=1,
        db=session,
        settings=Settings(),
    )
    assert first.headers["ETag"] == '"2"'

    with pytest.raises(ConflictError):
        update_role(
            role_id,
            RoleUpdate(name="Packer (night)"),
            principal,
            Response(),
            expected_version=1,
            db=session,
            settings=Settings(),
        )


def test_an_update_naming_no_version_is_still_accepted() -> None:
    """The precondition is opt-in: existing clients keep working."""
    session = _session()
    principal = _principal()
    role_id, _ = _role(session, principal)

    updated = update_role(
        role_id,
        RoleUpdate(name="Packer (any)"),
        principal,
        Response(),
        db=session,
        settings=Settings(),
    )
    assert updated.data is not None
    assert updated.data.name == "Packer (any)"
    assert updated.data.version == 2


def test_a_template_edit_changing_only_its_roles_moves_its_version() -> None:
    """A roles-only edit is an edit, so a stale `If-Match` must catch it.

    The bundle lives in `user_template_roles`, and the only header column the
    edit wrote was `updated_by` -- unchanged when the same person saves twice,
    so no UPDATE reached the template and its version stood still.
    """
    session = _session()
    service = IdentityService(session, Settings())
    actor = uuid4()
    roles = {
        code: session.scalar(select(Role.id).where(Role.code == code))
        for code in ("CASHIER", "VIEWER")
    }
    template = service.create_user_template(
        UserTemplateCreate(code="counter", name="Counter", role_ids=[roles["CASHIER"]]),
        actor,
    )
    before = template.version

    service.update_user_template(
        template.id, UserTemplateUpdate(role_ids=[roles["VIEWER"]]), actor
    )

    assert template.version == before + 1
