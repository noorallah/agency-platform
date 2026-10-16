"""Request-scoped context propagated through the current execution flow."""

from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass(slots=True)
class RequestActor:
    """What authentication learned about who is acting, filled in mid-request.

    Mutable, and held by the frozen `RequestContext`, because it is learned
    inside a dependency: FastAPI runs a sync dependency in a worker thread on
    a *copy* of the context, so a `ContextVar` set there never reaches the
    handler -- a change to an object both share does.
    """

    #: Set when the signed-in account is the support account (backlog 29s),
    #: so `record_audit` marks every row the request writes.
    by_support: bool = False


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Carry cross-cutting request metadata without coupling it to FastAPI."""

    request_id: str
    correlation_id: str
    client_ip: str | None
    requested_at: datetime
    user_id: UUID | None = None
    firm_id: UUID | None = None
    actor: RequestActor = field(default_factory=RequestActor)


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


def mark_support_actor() -> None:
    """Record that the support account is the one acting in this request.

    Outside a request (the CLI, a script) there is nobody signed in and
    nothing to mark.
    """
    context = _request_context.get()
    if context is not None:
        context.actor.by_support = True


#: The key under ``Session.info`` naming the firm whose store a session was
#: opened on. `get_db` and `firm_store_session` set it; `record_audit` reads it
#: so a write that names no firm still lands on that firm's trail, which
#: filters on `firm_id`. Kept here rather than beside `get_db` so the audit
#: service can read it without importing the tenancy machinery.
STORE_FIRM_SESSION_KEY = "store_firm_id"
