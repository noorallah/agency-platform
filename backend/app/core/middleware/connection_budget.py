"""Admit only as many requests as the connection pool can serve whole.

A firm-owned request holds more than one pooled connection at once: the
platform session that resolves the caller and the firm scope, and the firm's
own session -- which, for a firm stored on the platform server, comes out of
the **same** pool. When more requests arrive together than the pool can give
all of their connections to, each takes its first connection and waits for the
next; nobody finishes, nothing is returned, and every one of them fails after
the pool timeout. The desktop's Home screen opens about thirty reads at once,
so a single person signing in did exactly that: thirty requests, thirty 503s
after thirty seconds (D-PERF-2).

The cure is to queue requests *before* they hold anything. A request waits
here, holding no connection, until a slot is free; once admitted it can always
get every connection it needs, so the pool can no longer deadlock on itself.
"""

import asyncio

from starlette.types import ASGIApp, Receive, Scope, Send

# The most pooled connections one request holds at the same time: the
# platform session, the firm session, and a short platform read made while
# both are open (`platform_reader`, the tenant resolver).
CONNECTIONS_PER_REQUEST = 3

# Paths that never touch the database.
_FREE_PATHS = frozenset({"/health"})


def request_slots(pool_size: int, max_overflow: int) -> int:
    """Return how many requests the pool can serve at once without deadlock.

    Args:
        pool_size: The pool's resident connections.
        max_overflow: Connections it may open beyond them.

    Returns:
        The number of requests to admit together, at least one.

    """
    return max(1, (pool_size + max_overflow) // CONNECTIONS_PER_REQUEST)


class ConnectionBudgetMiddleware:
    """Hold each HTTP request until the pool can give it all its connections."""

    def __init__(self, app: ASGIApp, *, slots: int) -> None:
        """Wrap ``app``, admitting at most ``slots`` requests together.

        Args:
            app: The application to wrap.
            slots: How many requests may be in flight at once.

        """
        self.app = app
        self.slots = slots
        self._semaphore: asyncio.Semaphore | None = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Admit the request when a slot is free, and release it when done."""
        if scope["type"] != "http" or scope.get("path") in _FREE_PATHS:
            await self.app(scope, receive, send)
            return
        if self._semaphore is None:
            # Created on first use, inside the server's event loop.
            self._semaphore = asyncio.Semaphore(self.slots)
        async with self._semaphore:
            await self.app(scope, receive, send)
