"""Request-scoped context propagated through the current execution flow."""

from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Carry cross-cutting request metadata without coupling it to FastAPI."""

    request_id: str
    correlation_id: str
    client_ip: str | None
    requested_at: datetime
    user_id: UUID | None = None
    firm_id: UUID | None = None


_request_context: ContextVar[RequestContext | None] = ContextVar(
    "request_context", default=None
)


def set_request_context(context: RequestContext) -> Token[RequestContext | None]:
    """Set the context for the current request execution flow."""
    return _request_context.set(context)


def reset_request_context(token: Token[RequestContext | None]) -> None:
    """Restore the context that was active before the current request."""
    _request_context.reset(token)


def get_request_context() -> RequestContext | None:
    """Return the active request context, if execution is request-scoped."""
    return _request_context.get()
