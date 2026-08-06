"""Reusable FastAPI authorization dependencies for future API modules."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config.settings import Settings
from app.core.database.dependencies import get_platform_db
from app.core.enums import TokenType
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.security.jwt import JwtService, TokenClaims
from app.core.utils.dates import utc_now
from app.identity.models import User

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class Principal:
    """Represent the authenticated token subject and granted capabilities."""

    subject: UUID | str
    roles: frozenset[str]
    permissions: frozenset[str]
    claims: TokenClaims
    firm_id: UUID | None = None
    firm_permissions: Mapping[UUID, frozenset[str]] = field(
        default_factory=lambda: MappingProxyType({})
    )

    @property
    def is_platform_admin(self) -> bool:
        """Return whether the principal holds the immutable platform designation."""
        return "platform_admin" in self.roles

    def has_permission(self, permission: str) -> bool:
        """Check global or selected-firm permission grants."""
        if self.is_platform_admin or permission in self.permissions:
            return True
        return (
            self.firm_id is not None
            and permission in self.firm_permissions.get(self.firm_id, frozenset())
        )


def get_current_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_platform_db),
) -> Principal:
    """Validate a bearer access token and expose its generic authorization data."""
    if credentials is None:
        raise AuthenticationError()

    settings = request.app.state.settings
    if not isinstance(settings, Settings):
        raise RuntimeError("Application settings are not configured.")
    claims = JwtService(settings.jwt).validate_token(
        credentials.credentials, expected_type=TokenType.ACCESS
    )
    extra_claims = claims.model_extra or {}
    subject = _parse_subject(claims.subject)
    if not isinstance(subject, UUID):
        raise AuthenticationError()
    user = db.scalar(
        select(User).where(User.id == subject, User.is_deleted.is_(False))
    )
    now = utc_now()
    if (
        user is None
        or not user.is_active
        or (user.expires_at is not None and user.expires_at <= now)
        or int(extra_claims.get("authorization_version", 0))
        != user.authorization_version
    ):
        raise AuthenticationError()
    firm_id = _selected_firm_id(request)
    return Principal(
        subject=subject,
        roles=frozenset(_string_claims(extra_claims.get("roles"))),
        permissions=frozenset(_string_claims(extra_claims.get("permissions"))),
        claims=claims,
        firm_id=firm_id,
        firm_permissions=_firm_permission_claims(
            extra_claims.get("firm_permissions")
        ),
    )


def require_authenticated() -> Callable[[Principal], Principal]:
    """Return a dependency requiring any valid access token."""

    def dependency(
        principal: Principal = Depends(get_current_principal),
    ) -> Principal:
        return principal

    return dependency


def require_role(*required_roles: str) -> Callable[[Principal], Principal]:
    """Return a dependency requiring at least one declared role."""
    required = frozenset(required_roles)
    if not required:
        raise ValueError("At least one role is required.")

    def dependency(
        principal: Principal = Depends(get_current_principal),
    ) -> Principal:
        if principal.roles.isdisjoint(required):
            raise AuthorizationError()
        return principal

    return dependency


def require_platform_admin() -> Callable[[Principal], Principal]:
    """Return a dependency requiring the non-configurable platform-admin claim."""

    def dependency(
        principal: Principal = Depends(get_current_principal),
    ) -> Principal:
        extra_claims = principal.claims.model_extra or {}
        if "platform_admin" not in principal.roles or bool(
            extra_claims.get("password_change_required")
        ):
            raise AuthorizationError()
        return principal

    return dependency


def require_permission(*required_permissions: str) -> Callable[[Principal], Principal]:
    """Return a dependency requiring all declared permissions."""
    required = frozenset(required_permissions)
    if not required:
        raise ValueError("At least one permission is required.")

    def dependency(
        principal: Principal = Depends(get_current_principal),
    ) -> Principal:
        if _requires_password_change(principal) or not all(
            principal.has_permission(permission) for permission in required
        ):
            raise AuthorizationError()
        return principal

    return dependency


def require_any_permission(
    *required_permissions: str,
) -> Callable[[Principal], Principal]:
    """Return a dependency requiring at least one declared permission."""
    required = frozenset(required_permissions)
    if not required:
        raise ValueError("At least one permission is required.")

    def dependency(
        principal: Principal = Depends(get_current_principal),
    ) -> Principal:
        if _requires_password_change(principal) or not any(
            principal.has_permission(permission) for permission in required
        ):
            raise AuthorizationError()
        return principal

    return dependency


def _parse_subject(subject: str) -> UUID | str:
    """Use UUID subjects where possible while preserving future subject types."""
    try:
        return UUID(subject)
    except ValueError:
        return subject


def _requires_password_change(principal: Principal) -> bool:
    """Return whether the token is restricted to password-change operations."""
    extra_claims = principal.claims.model_extra or {}
    return bool(extra_claims.get("password_change_required"))


def _string_claims(value: object) -> tuple[str, ...]:
    """Safely normalize optional list-like authorization claims."""
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return tuple(value)
    return ()


def _selected_firm_id(request: Request) -> UUID | None:
    value = request.headers.get("X-Firm-ID")
    if value is None:
        return None
    try:
        return UUID(value)
    except ValueError as error:
        raise AuthorizationError(
            "X-Firm-ID must be a valid firm identifier."
        ) from error


def _firm_permission_claims(
    value: object,
) -> Mapping[UUID, frozenset[str]]:
    if not isinstance(value, dict):
        return MappingProxyType({})
    result: dict[UUID, frozenset[str]] = {}
    for firm_id, permissions in value.items():
        try:
            parsed_id = UUID(firm_id)
        except (TypeError, ValueError):
            continue
        result[parsed_id] = frozenset(_string_claims(permissions))
    return MappingProxyType(result)
