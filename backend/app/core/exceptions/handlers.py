"""FastAPI exception handlers for shared application errors."""

import logging
import traceback

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm.exc import StaleDataError

from app.core.context import get_request_context
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


async def unhandled_exception_handler(
    request: Request, exception: Exception
) -> JSONResponse:
    """Log an unexpected exception and return a safe server error."""
    logger.exception("Unhandled application exception", exc_info=exception)
    _persist_server_error(request, exception)
    return _error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code=ErrorCode.INTERNAL_SERVER_ERROR,
        message="An unexpected error occurred.",
    )


def request_id_for(request: Request) -> str | None:
    """Return the request id the caller was given, for an error handler.

    **The request object, not the context variable.** A handler registered for
    bare ``Exception`` is served by Starlette's ``ServerErrorMiddleware``, which
    sits at the very outside of the stack -- outside ``CoreRequestMiddleware``,
    whose ``finally`` has already reset the context variable by the time a 500
    reaches here. Reading the variable therefore returned None every time: all
    28 server faults recorded on this deployment carry a NULL request id, so the
    join from a user's screenshot to the traceback -- the thing the diagnostics
    module exists for -- could never be made.

    ``request.state`` is set on the request object itself and outlives the
    middleware that set it. The context variable stays as the fallback for a
    caller that has one and no request.
    """
    context = getattr(request.state, "context", None)
    if context is None:
        context = get_request_context()
    return None if context is None else context.request_id


def _persist_server_error(request: Request, exception: Exception) -> None:
    """Record an unhandled failure against the request id the caller was given.

    The client is told a `requestId` on every response, so a user's screenshot
    joins straight to this row -- which is the difference between "it broke" and
    a traceback.

    Opens its **own** platform session. The request's session is part of what
    just failed and may be in a broken transaction, and reusing it would make
    the write fail exactly when it is needed.

    Every failure here is swallowed: this runs while the request is already
    failing, and a diagnostics write that raised would replace a useful 500 with
    a confusing one.
    """
    try:
        from app.core.database.engine import DatabaseManager
        from app.diagnostics.services import ErrorReportService

        database = getattr(request.app.state, "database", None)
        if not isinstance(database, DatabaseManager):
            return
        sessions = database.sessions(schema=database.config.default_schema)
        with sessions.session() as session:
            ErrorReportService(session).record_server_error(
                error_type=type(exception).__name__,
                message=str(exception) or type(exception).__name__,
                stack_trace="".join(
                    traceback.format_exception(
                        type(exception), exception, exception.__traceback__
                    )
                ),
                request_id=request_id_for(request),
                context_label=f"{request.method} {request.url.path}"[:200],
            )
    except Exception:  # noqa: BLE001 - never mask the original failure
        logger.debug("Could not persist the server error report", exc_info=True)


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
