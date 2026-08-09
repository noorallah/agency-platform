"""Tests for the platform identity hardening changes."""

import re
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.common.audit.models import AuditLog
from app.core.config.settings import Settings
from app.core.database.base import Base
from app.core.exceptions import AuthenticationError, ConflictError
from app.core.utils.dates import utc_now
from app.identity.models import (
    LoginHistory,
    PasswordHistory,
    RefreshToken,
    User,
)
from app.identity.schemas.api import UserCreate
from app.identity.services import IdentityRetentionService, IdentityService
from app.identity.system_seed import ROLE_PERMISSION_CODES, SYSTEM_PERMISSION_CODES

PASSWORD = "Str0ng-Passw0rd!"


def _service() -> tuple[IdentityService, Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    return IdentityService(session, Settings()), session


def _user(service: IdentityService, email: str = "person@example.com") -> User:
    return service.create_user(
        UserCreate(email=email, full_name="Person", password=PASSWORD),
        actor_id=uuid4(),
    )


def _enforced_permission_codes() -> dict[str, str]:
    """Collect every literal permission code enforced anywhere under ``app``.

    The pattern deliberately accepts *any* string literal rather than only
    upper-snake-case ones. An earlier version matched ``[A-Z0-9_]+``, which made
    the lowercase ``sales_invoice:read`` codes in the sales-invoice router
    invisible to this guard while they silently locked the whole module to
    platform administrators.

    Returns:
        A mapping of permission code to the first file that enforces it.

    """
    used: dict[str, str] = {}
    for path in Path("app").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for match in re.finditer(
            r'require_(?:any_)?permission\(\s*((?:"[^"]*"\s*,?\s*)+)\)', source
        ):
            for code in re.findall(r'"([^"]*)"', match.group(1)):
                used.setdefault(code, str(path))
        for match in re.finditer(r'_permission\(\s*"([^"]*)"\s*\)', source):
            used.setdefault(match.group(1), str(path))
    return used


def test_enforced_permission_codes_follow_the_naming_convention() -> None:
    """Permission codes are upper snake case ``DOMAIN_ACTION`` identifiers.

    A code in any other shape cannot match the seeded catalogue, so the
    endpoint enforcing it becomes platform-admin-only.
    """
    malformed = {
        code: where
        for code, where in _enforced_permission_codes().items()
        if re.fullmatch(r"[A-Z][A-Z0-9_]*", code) is None
    }
    assert not malformed, f"permission codes must be upper snake case: {malformed}"


def test_every_enforced_permission_code_is_seeded() -> None:
    """No router may enforce a permission the catalogue does not define.

    An unseeded code cannot be attached to a role, so the endpoint silently
    becomes platform-admin-only.
    """
    catalogue = set(SYSTEM_PERMISSION_CODES)
    missing = {
        code: where
        for code, where in _enforced_permission_codes().items()
        if code not in catalogue
    }
    assert not missing, f"permission codes enforced but never seeded: {missing}"


def test_batch_and_delivery_permissions_reach_operational_roles() -> None:
    """The previously-missing codes are grantable through system roles."""
    firm_admin = ROLE_PERMISSION_CODES["FIRM_ADMIN"]
    inventory = ROLE_PERMISSION_CODES["INVENTORY_MANAGER"]
    for code in ("BATCH_VIEW", "SERIAL_VIEW", "SALES_CREATE", "SALES_EXPORT"):
        assert code in firm_admin, code
    for code in ("BATCH_CREATE", "SERIAL_UPDATE"):
        assert code in inventory, code


def test_unknown_email_login_still_verifies_a_hash() -> None:
    """An unknown address performs password verification to equalise timing."""
    service, _ = _service()
    calls: list[str] = []
    original = service._passwords.verify_password

    def spy(password: str, password_hash: str) -> bool:
        calls.append(password_hash)
        return original(password, password_hash)

    service._passwords.verify_password = spy  # type: ignore[method-assign]
    with pytest.raises(AuthenticationError):
        service.login("nobody@example.com", PASSWORD, client_ip=None, user_agent=None)
    assert len(calls) == 1
    assert calls[0].startswith("$argon2")


def test_soft_deleted_user_releases_its_email() -> None:
    """A leaver's address becomes available again for re-onboarding."""
    service, session = _service()
    actor = uuid4()
    user = _user(service, "leaver@example.com")
    service.delete_user(user.id, actor_id=actor)

    rehired = service.create_user(
        UserCreate(email="leaver@example.com", full_name="Rehire", password=PASSWORD),
        actor_id=actor,
    )
    assert rehired.id != user.id
    assert session.get(User, user.id).is_deleted is True

    # A live address is still protected.
    with pytest.raises(ConflictError):
        service.create_user(
            UserCreate(
                email="leaver@example.com", full_name="Clash", password=PASSWORD
            ),
            actor_id=actor,
        )


def test_refresh_token_reuse_revokes_every_session() -> None:
    """Replaying a rotated token is treated as compromise."""
    service, session = _service()
    user = _user(service)
    session.query(User).filter(User.id == user.id).update(
        {"force_password_change": False}
    )
    session.commit()

    first = service.login(user.email, PASSWORD, client_ip=None, user_agent=None)
    second = service.refresh(first.refresh_token)
    version_before = session.get(User, user.id).authorization_version

    # Replaying the already-rotated token must not merely fail.
    with pytest.raises(AuthenticationError):
        service.refresh(first.refresh_token)

    session.expire_all()
    assert session.get(User, user.id).authorization_version > version_before
    live = session.scalars(
        select(RefreshToken).where(
            RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)
        )
    ).all()
    assert live == [], "the successor session must be revoked too"

    # The successor token is dead as well.
    with pytest.raises(AuthenticationError):
        service.refresh(second.refresh_token)

    actions = set(
        session.scalars(
            select(AuditLog.action).where(AuditLog.entity_type == "user")
        ).all()
    )
    assert "identity.refresh_token_reuse_detected" in actions


def test_retention_prunes_expired_tokens_and_aged_history() -> None:
    """Retention removes stale rows and keeps the ones still in use."""
    service, session = _service()
    user = _user(service)
    now = utc_now()

    session.add_all(
        [
            RefreshToken(
                user_id=user.id,
                token_hash="expired-long-ago",
                expires_at=now - timedelta(days=30),
            ),
            RefreshToken(
                user_id=user.id,
                token_hash="still-valid",
                expires_at=now + timedelta(days=5),
            ),
            LoginHistory(
                user_id=user.id,
                attempted_email=user.email,
                outcome="success",
                created_at=now - timedelta(days=400),
            ),
            LoginHistory(
                user_id=user.id,
                attempted_email=user.email,
                outcome="success",
                created_at=now - timedelta(days=10),
            ),
        ]
    )
    for index in range(13):
        session.add(
            PasswordHistory(
                user_id=user.id,
                password_hash=f"hash-{index}",
                created_at=now - timedelta(days=index),
            )
        )
    session.commit()

    preview = IdentityRetentionService(session).purge(dry_run=True)
    assert preview.refresh_tokens == 1
    assert preview.login_history == 1
    assert preview.password_history == 3
    assert (
        session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == "expired-long-ago")
        )
        is not None
    )

    applied = IdentityRetentionService(session).purge()
    assert (applied.refresh_tokens, applied.login_history) == (1, 1)
    assert applied.password_history == 3

    remaining_tokens = session.scalars(select(RefreshToken.token_hash)).all()
    assert "still-valid" in remaining_tokens
    assert "expired-long-ago" not in remaining_tokens
    assert len(session.scalars(select(PasswordHistory.id)).all()) == 10


def test_retention_rejects_a_zero_password_history_window() -> None:
    """Keeping zero password hashes would disable the reuse check."""
    _, session = _service()
    with pytest.raises(ValueError, match="at least 1"):
        IdentityRetentionService(session).purge(password_history_keep=0)


def test_retention_clears_successor_links_before_deleting() -> None:
    """A rotated token can be pruned even while a successor references it."""
    service, session = _service()
    user = _user(service)
    now = utc_now()
    old = RefreshToken(
        user_id=user.id,
        token_hash="old-rotated",
        expires_at=now - timedelta(days=30),
        revoked_at=now - timedelta(days=30),
    )
    session.add(old)
    session.flush()
    successor = RefreshToken(
        user_id=user.id,
        token_hash="successor",
        expires_at=now + timedelta(days=5),
        replaced_by_id=None,
    )
    session.add(successor)
    session.flush()
    successor.replaced_by_id = old.id
    session.commit()

    result = IdentityRetentionService(session).purge()
    assert result.refresh_tokens == 1
    session.expire_all()
    assert session.get(RefreshToken, old.id) is None
    assert session.get(RefreshToken, successor.id).replaced_by_id is None


def test_user_ids_remain_uuids_after_rehire() -> None:
    """Guard the helper assumption used by the email-release test."""
    service, _ = _service()
    user = _user(service, "typed@example.com")
    assert isinstance(user.id, UUID)
