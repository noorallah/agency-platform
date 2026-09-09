"""Stable, centralized machine-readable application error codes."""

from enum import StrEnum


class ErrorCode(StrEnum):
    """Identify API failures without coupling clients to error messages."""

    VALIDATION_ERROR = "validation_error"
    AUTHENTICATION_REQUIRED = "authentication_required"
    #: Refusals that name the account's state. A wrong password stays
    #: AUTHENTICATION_REQUIRED with one message whatever the cause, so an
    #: outsider cannot learn which addresses exist; these three disclose that
    #: the account exists on purpose, because the person holding the right
    #: password needs to know what to do next (docs/BACKLOG.md 18.1, 18.2).
    ACCOUNT_LOCKED = "account_locked"
    ACCOUNT_INACTIVE = "account_inactive"
    ACCOUNT_EXPIRED = "account_expired"
    AUTHORIZATION_DENIED = "authorization_denied"
    RESOURCE_NOT_FOUND = "resource_not_found"
    RESOURCE_CONFLICT = "resource_conflict"
    BUSINESS_RULE_VIOLATION = "business_rule_violation"
    DATABASE_ERROR = "database_error"
    LICENSE_ERROR = "license_error"
    EXTERNAL_SERVICE_ERROR = "external_service_error"
    HTTP_ERROR = "http_error"
    INTERNAL_SERVER_ERROR = "internal_server_error"
