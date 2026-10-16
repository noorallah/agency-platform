"""The one named support account an installed copy carries (backlog 29s).

The vendor's support person needs to reach every firm on a customer's
installation without borrowing the customer's own administrator. That is one
named account holding the ``ALL_FIRMS`` platform designation, created on the
machine itself by ``agency-server create-support-admin`` -- no API route and
no screen creates it, so nobody signed in to the product can mint a second.

The password is supplied by the caller and is only ever hashed here; it is
never printed, logged or written to the audit trail.
"""

from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.audit.services import record_audit
from app.core.enums import PlatformAdminScope
from app.core.exceptions import ConflictError
from app.core.security import PasswordSecurity
from app.core.utils.dates import utc_now
from app.core.validation import validate_email, validate_password_policy
from app.identity.models import PlatformAdmin, RefreshToken, User

#: Written to ``users.department`` so the account reads as support on the
#: Users screen. Display only: what marks the account is
#: ``users.is_support_account`` (part c), which only this module writes --
#: a customer may well have a department called Support of their own.
SUPPORT_DEPARTMENT = "Support"


class SupportAdminOutcome(StrEnum):
    """What ``ensure_support_admin`` did."""

    CREATED = "created"
    EXISTS = "exists"
    PASSWORD_RESET = "password-reset"


@dataclass(frozen=True)
class SupportAdminResult:
    """The outcome and the account it concerns."""

    outcome: SupportAdminOutcome
    email: str


def ensure_support_admin(
    session: Session,
    *,
    email: str,
    full_name: str,
    password: str | None,
    reset_password: bool = False,
) -> SupportAdminResult:
    """Create the support account, or report that it is already there.

    Idempotent: an existing support account is left exactly as it is unless
    ``reset_password`` is set. An address held by any other live account --
    an ordinary user, a ``PLATFORM`` operator, or a customer's own
    ``ALL_FIRMS`` administrator, none of them marked -- is refused rather
    than promoted, because widening somebody's reach is not what this command
    was asked to do. ``password`` may be ``None`` only when nothing needs one,
    which is the "already exists" answer.
    """
    normalized = validate_email(email)
    user = session.scalar(
        select(User).where(User.email == normalized, User.is_deleted.is_(False))
    )
    if user is not None:
        designation = session.scalar(
            select(PlatformAdmin).where(
                PlatformAdmin.user_id == user.id,
                PlatformAdmin.is_deleted.is_(False),
            )
        )
        if (
            not user.is_support_account
            or designation is None
            or designation.scope != PlatformAdminScope.ALL_FIRMS.value
        ):
            raise ConflictError(
                f"{normalized} belongs to an account that is not the support "
                "account; choose another address."
            )
        if not reset_password:
            return SupportAdminResult(SupportAdminOutcome.EXISTS, normalized)
        if password is None:
            raise ValueError("A password is needed to reset it.")
        validate_password_policy(password)
        user.password_hash = PasswordSecurity().hash_password(password)
        user.failed_login_attempts = 0
        user.locked_until = None
        # A reset ends every session the old password opened.
        user.authorization_version += 1
        now = utc_now()
        for token in session.scalars(
            select(RefreshToken).where(
                RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)
            )
        ):
            token.revoked_at = now
        record_audit(
            session,
            action="identity.support_admin_password_reset",
            entity_type="user",
            entity_id=user.id,
            actor_id=None,
        )
        session.commit()
        return SupportAdminResult(SupportAdminOutcome.PASSWORD_RESET, normalized)

    if password is None:
        raise ValueError("A password is needed to create the support account.")
    validate_password_policy(password)
    user = User(
        email=normalized,
        full_name=full_name.strip() or "Support",
        password_hash=PasswordSecurity().hash_password(password),
        is_active=True,
        force_password_change=False,
        department=SUPPORT_DEPARTMENT,
        is_support_account=True,
    )
    session.add(user)
    session.flush()
    session.add(
        PlatformAdmin(
            user_id=user.id,
            scope=PlatformAdminScope.ALL_FIRMS.value,
        )
    )
    record_audit(
        session,
        action="identity.support_admin_created",
        entity_type="user",
        entity_id=user.id,
        actor_id=None,
        after_data={
            "email": normalized,
            "platform_admin_scope": PlatformAdminScope.ALL_FIRMS.value,
        },
    )
    session.commit()
    return SupportAdminResult(SupportAdminOutcome.CREATED, normalized)
