"""Stable, centralized machine-readable application error codes."""

from enum import StrEnum


class ErrorCode(StrEnum):
    """Identify API failures without coupling clients to error messages."""

    VALIDATION_ERROR = "validation_error"
    AUTHENTICATION_REQUIRED = "authentication_required"
    AUTHORIZATION_DENIED = "authorization_denied"
    RESOURCE_NOT_FOUND = "resource_not_found"
    RESOURCE_CONFLICT = "resource_conflict"
    BUSINESS_RULE_VIOLATION = "business_rule_violation"
    DATABASE_ERROR = "database_error"
    LICENSE_ERROR = "license_error"
    EXTERNAL_SERVICE_ERROR = "external_service_error"
    HTTP_ERROR = "http_error"
    INTERNAL_SERVER_ERROR = "internal_server_error"
