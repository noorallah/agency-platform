"""The pool can no longer deadlock on a burst of requests (D-PERF-2).

Thirty requests at once -- the desktop's Home screen -- each took one pooled
connection and waited for a second, so all thirty failed after the pool
timeout. `ConnectionBudgetMiddleware` queues requests before they hold any.
"""

import asyncio

from starlette.types import Receive, Scope, Send

from app.core.middleware import ConnectionBudgetMiddleware, request_slots
from app.main import create_app


def _counting_app(slots: int) -> tuple[ConnectionBudgetMiddleware, dict[str, int]]:
    """Build an ASGI app that records how many requests run at once."""
    seen = {"now": 0, "most": 0}

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        """Hold the request open briefly, counting overlap."""
        seen["now"] += 1
        seen["most"] = max(seen["most"], seen["now"])
        await asyncio.sleep(0.01)
        seen["now"] -= 1

    return ConnectionBudgetMiddleware(app, slots=slots), seen


async def _call(app: ConnectionBudgetMiddleware, path: str) -> None:
    """Send one HTTP request through the middleware."""

    async def receive() -> dict[str, object]:
        """Never read."""
        return {"type": "http.request"}

    async def send(message: object) -> None:
        """Discard the answer."""

    await app({"type": "http", "path": path}, receive, send)  # type: ignore[arg-type]


async def _burst(app: ConnectionBudgetMiddleware, path: str, count: int) -> None:
    """Send ``count`` requests together."""
    await asyncio.gather(*(_call(app, path) for _ in range(count)))


def test_slots_leave_every_admitted_request_its_connections() -> None:
    """The default pool of 5 + 10 admits five requests of three connections."""
    assert request_slots(5, 10) == 5
    assert request_slots(1, 0) == 1


def test_a_burst_is_queued_rather_than_run_all_at_once() -> None:
    """Thirty requests together never run more than the slots allow."""
    app, seen = _counting_app(slots=4)
    asyncio.run(_burst(app, "/api/v1/quotations", 30))
    assert seen["most"] == 4


def test_the_liveness_probe_is_never_queued() -> None:
    """`/health` touches no database, so it is not held behind real work."""
    app, seen = _counting_app(slots=1)
    asyncio.run(_burst(app, "/health", 5))
    assert seen["most"] == 5


def test_the_application_installs_it() -> None:
    """`create_app` wraps every request in the budget."""
    app = create_app()
    assert any(m.cls is ConnectionBudgetMiddleware for m in app.user_middleware)
