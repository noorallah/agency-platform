"""Application exception types independent of HTTP transport."""

from app.core.error_codes import ErrorCode


class ApplicationError(Exception):
    """Base exception for expected application failures.

    Attributes:
        status_code: HTTP status suitable for the API adapter.
        code: Stable machine-readable error code.
        message: Safe message exposed by the API adapter.
        details: Optional structured information about the failure.

    """

    status_code = 400
    code = ErrorCode.INTERNAL_SERVER_ERROR
    message = "The request could not be completed."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: object | None = None,
    ) -> None:
        """Initialize an application error.

        Args:
            message: Optional safe message overriding the class default.
            details: Optional structured information for the API response.

        """
        self.message = message or self.message
        self.details = details
        super().__init__(self.message)


class ResourceNotFoundError(ApplicationError):
    """Represent a requested resource that does not exist."""

    status_code = 404
    code = ErrorCode.RESOURCE_NOT_FOUND
    message = "The requested resource was not found."


class ConflictError(ApplicationError):
    """Represent a conflict with the current resource state."""

    status_code = 409
    code = ErrorCode.RESOURCE_CONFLICT
    message = "The request conflicts with the current resource state."


class ValidationError(ApplicationError):
    """Represent invalid input or a reusable validation-rule failure."""

    status_code = 422
    code = ErrorCode.VALIDATION_ERROR
    message = "The request validation failed."


class BusinessRuleError(ApplicationError):
    """Represent a domain rule that prevents the requested operation."""

    status_code = 422
    code = ErrorCode.BUSINESS_RULE_VIOLATION
    message = "The request violates a business rule."


class ExternalServiceError(ApplicationError):
    """Represent a failed call to an external dependency."""

    status_code = 502
    code = ErrorCode.EXTERNAL_SERVICE_ERROR
    message = "An external service could not complete the request."


class AuthenticationError(ApplicationError):
    """Represent an absent, expired, or invalid authentication credential."""

    status_code = 401
    code = ErrorCode.AUTHENTICATION_REQUIRED
    message = "Authentication is required."


class AuthorizationError(ApplicationError):
    """Represent a valid identity lacking a required dynamic permission."""

    status_code = 403
    code = ErrorCode.AUTHORIZATION_DENIED
    message = "You do not have permission to perform this action."
