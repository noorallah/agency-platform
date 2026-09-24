"""What every dated report's tests share: a scope, and the HTTP-level refusal.

Every dated report takes ``from_date``/``to_date`` and ``page``/``page_size``
(D-RPT-18). The module tests call the handlers directly, the way the rest of
this suite does, which proves the window and the count but cannot prove the
bound: a handler called as a function never sees FastAPI's validation. So
`status_for` drives the route through the ASGI app itself, with the route's
dependencies stood in for, and reports the status FastAPI answers.

Not a test module (no ``test_`` prefix): the module tests import it.
"""

import asyncio
from typing import Any
from urllib.parse import urlencode
from uuid import UUID, uuid4

from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute

from app.common.scope import ResolvedFirmScope
from app.core.enums import TokenType
from app.core.security.authorization import Principal
from app.core.security.jwt import TokenClaims


def report_scope(firm_id: UUID) -> ResolvedFirmScope:
    """Return a scope on ``firm_id``; a report handler reads nothing else."""
    user_id = uuid4()
    return ResolvedFirmScope(
        principal=Principal(
            subject=user_id,
            roles=frozenset(),
            permissions=frozenset({"REPORT_VIEW"}),
            claims=TokenClaims(
                sub=str(user_id), type=TokenType.ACCESS, iat=1, exp=4_102_444_800
            ),
        ),
        firm_id=firm_id,
    )


def _stand_in() -> None:
    """Replace a dependency the refusal never reaches."""
    return None


def status_for(router: APIRouter, path: str, **query: object) -> int:
    """Return the status FastAPI answers ``GET path?query`` with.

    Only for a request FastAPI refuses before the handler runs: every
    dependency is stood in for, so a request it accepted would reach a handler
    with no session.
    """
    app = FastAPI()
    app.include_router(router)
    route = next(
        item
        for item in router.routes
        if isinstance(item, APIRoute) and item.path == path and "GET" in item.methods
    )
    for dependency in route.dependant.dependencies:
        if dependency.call is not None:
            app.dependency_overrides[dependency.call] = _stand_in
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        """Deliver an empty request body."""
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        """Keep what the app answers."""
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": urlencode({k: str(v) for k, v in query.items()}).encode(),
        "headers": [],
        "client": ("test", 1),
        "server": ("test", 80),
    }
    asyncio.run(app(scope, receive, send))
    start = next(item for item in sent if item["type"] == "http.response.start")
    return int(start["status"])


def assert_page_size_is_bounded(router: APIRouter, *paths: str) -> None:
    """Each of ``paths`` refuses a page above the cap, and a page below one.

    A 422 naming the limit, not the 500 a bound checked inside the handler
    answers (`test_pagination_conventions.py` says why).
    """
    for path in paths:
        assert status_for(router, path, page_size=101) == 422, path
        assert status_for(router, path, page=0) == 422, path
