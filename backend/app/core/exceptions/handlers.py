"""FastAPI exception handlers for shared application errors."""

import logging

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm.exc import StaleDataError

from app.core.error_codes import ErrorCode
from app.core.exceptions.base import ApplicationError
from app.core.responses.models import (
    ApiError,
    ErrorResponse,
    ValidationErrorDetail,
    ValidationErrorResponse,
)

logger = logging.getLogger(__name__)


def register_exception_handlers(application: FastAPI) -> None:
    """Register global exception handlers on an application.

    Args:
        application: FastAPI application to configure.

    """
    application.add_exception_handler(ApplicationError, application_error_handler)
    application.add_exception_handler(RequestValidationError, validation_error_handler)
    application.add_exception_handler(HTTPException, http_exception_handler)
    application.add_exception_handler(SQLAlchemyError, database_error_handler)
    application.add_exception_handler(Exception, unhandled_exception_handler)


async def application_error_handler(_: Request, exception: Exception) -> JSONResponse:
    """Serialize an expected application error."""
    if not isinstance(exception, ApplicationError):
        raise TypeError("Application error handler received an unexpected exception.")

    return _error_response(
        status_code=exception.status_code,
        code=exception.code,
        message=exception.message,
        details=exception.details,
    )


async def validation_error_handler(_: Request, exception: Exception) -> JSONResponse:
    """Serialize request validation errors using the standard error contract."""
    if not isinstance(exception, RequestValidationError):
        raise TypeError("Validation handler received an unexpected exception.")

    return _error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code=ErrorCode.VALIDATION_ERROR,
        message="The request validation failed.",
        details=[
            ValidationErrorDetail(
                field=".".join(str(segment) for segment in error["loc"]),
                message=error["msg"],
                code=error["type"],
            ).model_dump()
            for error in exception.errors()
        ],
        response_model=ValidationErrorResponse,
    )


async def http_exception_handler(_: Request, exception: Exception) -> JSONResponse:
    """Serialize framework HTTP errors using the standard error contract."""
    if not isinstance(exception, HTTPException):
        raise TypeError("HTTP exception handler received an unexpected exception.")

    detail = exception.detail
    message = (
        detail if isinstance(detail, str) else "The request could not be completed."
    )
    return _error_response(
        status_code=exception.status_code,
        code=ErrorCode.HTTP_ERROR,
        message=message,
        details=None if isinstance(detail, str) else detail,
    )


async def database_error_handler(_: Request, exception: Exception) -> JSONResponse:
    """Log database failures without exposing database implementation details."""
    if not isinstance(exception, SQLAlchemyError):
        raise TypeError("Database handler received an unexpected exception.")

    if isinstance(exception, StaleDataError):
        # The optimistic-concurrency counter rejected the write: another
        # transaction changed the row after this one loaded it.
        logger.warning("Concurrent update rejected", exc_info=exception)
        return _error_response(
            status_code=status.HTTP_409_CONFLICT,
            code=ErrorCode.RESOURCE_CONFLICT,
            message="This record changed since you loaded it. Reload and try again.",
        )

    if isinstance(exception, IntegrityError):
        # A losing race on a unique key — two concurrent creates allocating the
        # same document number, say — is a conflict the caller can retry, not a
        # database outage. Reporting 503 told clients the wrong thing.
        logger.warning("Database integrity conflict", exc_info=exception)
        return _error_response(
            status_code=status.HTTP_409_CONFLICT,
            code=ErrorCode.RESOURCE_CONFLICT,
            message="The request conflicts with existing data. Please retry.",
        )

    logger.exception("Database operation failed", exc_info=exception)
    return _error_response(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code=ErrorCode.DATABASE_ERROR,
        message="The database is temporarily unavailable.",
    )


async def unhandled_exception_handler(_: Request, exception: Exception) -> JSONResponse:
    """Log an unexpected exception and return a safe server error."""
    logger.exception("Unhandled application exception", exc_info=exception)
    return _error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code=ErrorCode.INTERNAL_SERVER_ERROR,
        message="An unexpected error occurred.",
    )


def _error_response(
    *,
    status_code: int,
    code: ErrorCode | str,
    message: str,
    details: object | None = None,
    response_model: type[ErrorResponse] = ErrorResponse,
) -> JSONResponse:
    """Build a JSON error response from normalized error fields."""
    payload = response_model(
        error=ApiError(code=code, message=message, details=details)
    ).model_dump(mode="json", by_alias=True, exclude_none=True)
    return JSONResponse(status_code=status_code, content=payload)
