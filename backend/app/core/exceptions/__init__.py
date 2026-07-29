"""Expected application errors and HTTP exception handlers."""

from app.core.exceptions.base import (
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
    "ApplicationError",
    "AuthenticationError",
    "AuthorizationError",
    "BusinessRuleError",
    "ConflictError",
    "ExternalServiceError",
    "ResourceNotFoundError",
    "ValidationError",
]
