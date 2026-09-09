"""Expected application errors and HTTP exception handlers."""

from app.core.exceptions.base import (
    AccountExpiredError,
    AccountInactiveError,
    AccountLockedError,
    ApplicationError,
    AuthenticationError,
    AuthorizationError,
    BusinessRuleError,
    ConflictError,
    ExternalServiceError,
    ResourceNotFoundError,
    ValidationError,
)

__all__ = [
    "AccountExpiredError",
    "AccountInactiveError",
    "AccountLockedError",
    "ApplicationError",
    "AuthenticationError",
    "AuthorizationError",
    "BusinessRuleError",
    "ConflictError",
    "ExternalServiceError",
    "ResourceNotFoundError",
    "ValidationError",
]
