"""Tests for the platform identity hardening changes."""

import base64
import io
import json
import re
import tokenize
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.common.audit.models import AuditLog
from app.core.config.settings import Settings
from app.core.database.base import Base
from app.core.exceptions import (
    AuthenticationError,
    BusinessRuleError,
    ConflictError,
    ValidationError,
)
from app.core.security.authorization import Principal
from app.core.utils.dates import utc_now
from app.identity.models import (
    LoginHistory,
    PasswordHistory,
    RefreshToken,
    Role,
    User,
    UserRole,
)
from app.identity.schemas.api import RoleCreate, UserCreate
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
        # `_permission_scope(` as well as `_permission(`: `firm_permission_scope`
        # is how most of this codebase enforces a code, and matching only the
        # shorter name left 138 of 157 enforced codes invisible to this guard.
        for match in re.finditer(r'_permission(?:_scope)?\(\s*"([^"]*)"\s*\)', source):
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


def test_creating_a_user_keeps_the_profile_fields_it_was_given() -> None:
    """A mobile number typed at creation has to survive the create.

    ``UserCreate`` carried only the six identity fields, and ``ApiSchema``
    forbids undeclared ones, so a client that sent a mobile number or a photo
    got a 422 -- and the desktop, which shows both boxes on the create form,
    had stopped sending them. The record was written blank and looked blank
    when it was opened again.
    """
    service, session = _service()

    user = service.create_user(
        UserCreate(
            email="hired@example.com",
            full_name="Newly Hired",
            password=PASSWORD,
            personal_mobile="+91 98765 43210",
            profile_photo_url="https://photos.example.test/hired.png",
            employee_code="EMP-0042",
            department="Sales",
        ),
        actor_id=uuid4(),
    )

    session.expire_all()
    stored = session.get(User, user.id)
    assert stored is not None
    assert stored.personal_mobile == "+91 98765 43210"
    assert stored.profile_photo_url == "https://photos.example.test/hired.png"
    assert stored.employee_code == "EMP-0042"
    assert stored.department == "Sales"


def test_every_profile_field_is_writable_at_creation() -> None:
    """Create and update write the same set, so neither can drift from it.

    The defect was exactly this drift: update wrote eighteen columns and
    create wrote none of them.
    """
    from app.identity.schemas.api import UserProfileFields
    from app.identity.services.identity_service import _PROFILE_FIELDS

    assert set(_PROFILE_FIELDS) == set(UserProfileFields.model_fields)
    assert set(_PROFILE_FIELDS) <= set(UserCreate.model_fields)


def _claims_of(token: str) -> dict[str, object]:
    """Decode a JWT payload without verifying it; the test signed it."""
    payload = token.split(".")[1]
    padded = payload + "=" * (-len(payload) % 4)
    decoded: dict[str, object] = json.loads(base64.urlsafe_b64decode(padded))
    return decoded


def test_a_role_cannot_spell_the_platform_designation() -> None:
    """A role code must not be able to become the platform-admin marker.

    The designation is appended to the `roles` claim as the lowercase string
    `"platform_admin"`, while genuine role codes are uppercase -- so the two
    namespaces share one list. `RoleCreate.code` is validated against
    `^[a-z0-9._-]+$`, which does not merely permit that spelling, it requires
    lowercase.

    So a firm administrator -- who holds both `ROLE_CREATE` and `ROLE_ASSIGN`
    -- could create a role called `platform_admin`, assign it to themselves,
    and sign in as a platform administrator: every check reads the claim as a
    plain string. That grants all 65 `require_platform_admin()` routes, every
    permission through the short-circuit in `Principal.has_permission`, and
    **every firm's data**, because `optional_firm_scope` skips the membership
    check for a platform admin.

    Two things are asserted, because either alone can be satisfied without
    closing the hole: the code is refused outright, and -- were one to exist
    already -- a token issued for it does not carry the designation.
    """
    service, session = _service()
    actor = uuid4()
    person = _user(service, email="firm.admin@example.com")

    with pytest.raises((BusinessRuleError, ConflictError, ValidationError)):
        service.create_role(
            RoleCreate(code="platform_admin", name="Not a designation"),
            actor_id=actor,
        )

    # And the claim itself: a role row written by any other route -- a
    # migration, a fixture, a future endpoint -- must still not confer it.
    smuggled = Role(
        code="platform_admin",
        name="Smuggled",
        is_active=True,
        is_system=False,
        created_by=actor,
        updated_by=actor,
    )
    session.add(smuggled)
    session.flush()
    session.add(
        UserRole(
            user_id=person.id,
            role_id=smuggled.id,
            created_by=actor,
            updated_by=actor,
        )
    )
    session.commit()

    tokens = service.login(person.email, PASSWORD, client_ip=None, user_agent=None)
    claims = _claims_of(tokens.access_token)
    assert (
        claims.get("platform_admin") is not True
    ), "a role row must not confer the platform designation"

    principal = Principal(
        subject=person.id,
        roles=frozenset(claims.get("roles") or []),
        permissions=frozenset(claims.get("permissions") or []),
        claims=SimpleNamespace(model_extra=claims),
    )
    assert not principal.is_platform_admin, (
        "holding a role called `platform_admin` made this principal a "
        "platform administrator"
    )


def test_no_module_reads_the_designation_out_of_the_roles_claim() -> None:
    """The designation is its own claim, and a grep is what keeps it that way.

    `test_a_role_cannot_spell_the_platform_designation` closed the escalation
    by moving the designation out of `roles`. It did not stop anything *else*
    still looking for it there -- and two places were, both in
    `app/common/audit/api/router.py`, spelled `"platform_admin" in
    principal.roles` rather than `principal.is_platform_admin`.

    The consequence was total and silent: the condition became permanently
    false, so **no platform administrator could read any audit trail**. The
    audit tests kept passing throughout, because their fixtures still built a
    principal with `roles={"platform_admin"}` -- the shape the application had
    stopped issuing. A fixture that supplies the old shape cannot see the
    break, which is why the suite going green after the escalation fix proved
    less than it looked like it did.

    Found on 2026-09-06 while reading the file for an unrelated reason, which
    is not a method. This is the method.
    """
    offenders: list[str] = []
    for path in sorted(Path("app").rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()
        # Comments are stripped before matching. A naive grep flags the
        # comment two files away that *warns* against this exact pattern --
        # the same false positive the `date.today()` sweep hit, recorded in
        # CLAUDE.md. A guard that cries wolf on its own documentation is one
        # somebody deletes.
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.COMMENT:
                row = token.start[0] - 1
                lines[row] = lines[row].replace(token.string, "")
        for number, line in enumerate(lines, start=1):
            if "platform_admin" in line and "principal.roles" in line:
                offenders.append(f"{path.as_posix()}:{number}: {line.strip()}")

    assert not offenders, (
        "these read the platform designation out of the `roles` claim, where "
        "it no longer is:"
        + "".join(f"\n  {offender}" for offender in offenders)
        + "\n\nUse `principal.is_platform_admin`, or "
        "`principal.may_act_in_any_firm` where the question is whether the "
        "caller may act inside a firm's books."
    )
