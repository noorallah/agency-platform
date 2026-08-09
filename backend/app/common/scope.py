"""Shared firm-scope resolution for firm-owned routes.

Nineteen routers each carry their own ~55-line copy of this logic. This module
is the single implementation they should collapse onto; it exists now because
``app/search`` had no copy at all, and a router that skips the membership check
will happily serve another firm's data to anyone who sets ``X-Firm-ID``.

It lives in ``app/common`` rather than ``app/core`` because it must reference the
``Firm`` and ``UserFirm`` entities, and the core framework stays free of business
entities.
"""

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database.dependencies import get_platform_db
from app.core.exceptions import AuthorizationError
from app.core.security.authorization import (
    Principal,
    get_current_principal,
    require_permission,
)
from app.firms.models import Firm
from app.identity.models import UserFirm


@dataclass(frozen=True, slots=True)
class FirmScope:
    """Carry the authenticated principal and the firm it may act on."""

    principal: Principal
    firm_id: UUID | None

    @property
    def actor_id(self) -> UUID:
        """Return the acting user id.

        Raises:
            RuntimeError: If the principal is not a user.

        """
        if not isinstance(self.principal.subject, UUID):
            raise RuntimeError("This operation requires a user principal.")
        return self.principal.subject


@dataclass(frozen=True, slots=True)
class ResolvedFirmScope:
    """A firm scope that is guaranteed to carry a firm."""

    principal: Principal
    firm_id: UUID

    @property
    def actor_id(self) -> UUID:
        """Return the acting user id.

        Raises:
            RuntimeError: If the principal is not a user.

        """
        if not isinstance(self.principal.subject, UUID):
            raise RuntimeError("This operation requires a user principal.")
        return self.principal.subject


def optional_firm_scope(
    principal: Annotated[Principal, Depends(get_current_principal)],
    db: Annotated[Session, Depends(get_platform_db)],
    x_firm_id: Annotated[UUID | None, Header(alias="X-Firm-ID")] = None,
) -> FirmScope:
    """Resolve firm scope, allowing requests that carry no firm at all.

    A supplied firm is always validated: it must be active, and unless the caller
    is a platform administrator they must hold an active membership in it.
    Requests with no ``X-Firm-ID`` resolve to a null scope so platform-wide
    surfaces keep working; callers are responsible for restricting what a null
    scope may read.

    The firm registry lives only in the platform schema, so membership is checked
    against a platform session rather than the request's tenant session.

    Args:
        principal: The authenticated caller.
        db: A platform-schema session.
        x_firm_id: The requested firm context.

    Returns:
        The resolved firm scope.

    Raises:
        AuthorizationError: If the firm is unavailable or not the caller's.

    """
    if x_firm_id is None:
        return FirmScope(principal=principal, firm_id=None)
    firm = db.scalar(
        select(Firm.id).where(
            Firm.id == x_firm_id,
            Firm.is_active.is_(True),
            Firm.is_deleted.is_(False),
        )
    )
    if firm is None:
        raise AuthorizationError("The selected firm is inactive or unavailable.")
    if principal.is_platform_admin:
        return FirmScope(principal=principal, firm_id=x_firm_id)
    if not isinstance(principal.subject, UUID):
        raise AuthorizationError("An authorized active firm is required.")
    membership = db.scalar(
        select(UserFirm.id).where(
            UserFirm.user_id == principal.subject,
            UserFirm.firm_id == x_firm_id,
            UserFirm.is_active.is_(True),
            UserFirm.is_deleted.is_(False),
        )
    )
    if membership is None:
        raise AuthorizationError("You are not authorized for the selected firm.")
    return FirmScope(principal=principal, firm_id=x_firm_id)


def required_firm_scope(
    scope: Annotated[FirmScope, Depends(optional_firm_scope)],
) -> ResolvedFirmScope:
    """Resolve firm scope, refusing requests that carry no firm.

    Args:
        scope: The optionally-scoped result.

    Returns:
        The resolved firm scope, guaranteed to carry a firm.

    Raises:
        AuthorizationError: If no firm context was supplied.

    """
    if scope.firm_id is None:
        raise AuthorizationError("X-Firm-ID is required for firm-owned resources.")
    return ResolvedFirmScope(principal=scope.principal, firm_id=scope.firm_id)


def firm_permission_scope(code: str) -> object:
    """Compose a permission check with firm-scope resolution.

    Every firm-owned router declared its own copy of this pair. Beyond the
    duplication, those copies resolved ``Firm`` and ``UserFirm`` on the *tenant*
    session, and those tables exist only in the platform store — so on
    PostgreSQL the check raised ``UndefinedTable`` for every firm whose data does
    not live in the platform schema. Resolving through ``get_platform_db`` here
    is what makes the check work at all outside SQLite tests.

    Args:
        code: The permission code the caller must hold.

    Returns:
        A FastAPI dependency yielding the resolved firm scope.

    """

    def dependency(
        _: Annotated[Principal, Depends(require_permission(code))],
        scope: Annotated[ResolvedFirmScope, Depends(required_firm_scope)],
    ) -> ResolvedFirmScope:
        return scope

    return Depends(dependency)


OptionalFirmScope = Annotated[FirmScope, Depends(optional_firm_scope)]
RequiredFirmScope = Annotated[ResolvedFirmScope, Depends(required_firm_scope)]
