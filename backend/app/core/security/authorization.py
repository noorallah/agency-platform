"""Reusable FastAPI authorization dependencies for future API modules."""

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config.settings import Settings
from app.core.enums import TokenType
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.security.jwt import JwtService, TokenClaims

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class Principal:
    """Represent the authenticated token subject and granted capabilities."""

    subject: UUID | str
    roles: frozenset[str]
    permissions: frozenset[str]
    claims: TokenClaims


def get_current_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
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
    return Principal(
        subject=subject,
        roles=frozenset(_string_claims(extra_claims.get("roles"))),
        permissions=frozenset(_string_claims(extra_claims.get("permissions"))),
        claims=claims,
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
        if _requires_password_change(principal) or not required.issubset(
            principal.permissions
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
        if _requires_password_change(principal) or principal.permissions.isdisjoint(
            required
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
