"""A report opens to whoever may read its module, or holds ``REPORT_VIEW``.

The desktop's Reports screen is offered on ``REPORT_VIEW``, a seeded code no
route enforced, while every report route took its module's own view code. An
``ACCOUNTANT`` holds the ``report`` group and none of the module codes, so it
was offered the screen and refused (403) every operational entry on it --
driven on TEST01 on 2026-09-23 (D-RPT-4). Every ``/reports/`` route now accepts
``REPORT_VIEW`` beside the module's code, through ``firm_any_permission_scope``.
"""

from collections.abc import Iterator
from uuid import uuid4

import pytest

from app.common.scope import firm_any_permission_scope
from app.core.enums import TokenType
from app.core.exceptions import AuthorizationError
from app.core.security.authorization import Principal, require_any_permission
from app.core.security.jwt import TokenClaims


def _endpoints(routes: object) -> Iterator[object]:
    """Yield the leaf endpoints of a built application (see test_document_framework)."""
    for route in routes:  # type: ignore[attr-defined]
        inner = getattr(route, "original_router", None)
        if inner is not None:
            yield from _endpoints(inner.routes)
            continue
        nested = getattr(route, "routes", None)
        if nested:
            yield from _endpoints(nested)
            continue
        yield route


def _codes_accepted_by(route: object) -> set[str]:
    """Return every code the route's dependency tree records as opening it."""
    codes: set[str] = set()
    dependant = getattr(route, "dependant", None)
    pending = list(dependant.dependencies) if dependant is not None else []
    while pending:
        dependency = pending.pop()
        for code in getattr(dependency.call, "permission_codes", ()):
            codes.add(code)
        single = getattr(dependency.call, "permission_code", None)
        if single:
            codes.add(single)
        pending.extend(dependency.dependencies)
    return codes


def _principal(*permissions: str) -> Principal:
    subject = uuid4()
    return Principal(
        subject=subject,
        roles=frozenset(),
        permissions=frozenset(permissions),
        claims=TokenClaims(
            sub=str(subject),
            type=TokenType.ACCESS,
            iat=1,
            exp=4_102_444_800,
            roles=[],
            permissions=sorted(permissions),
        ),
    )


def test_every_report_route_accepts_report_view() -> None:
    """The catalogue's gate and the routes' gate name the same code."""
    from app.main import create_app

    report_routes = [
        route
        for route in _endpoints(create_app().routes)
        if "/reports/" in getattr(route, "path", "")
    ]
    assert report_routes, "no report routes found"
    refusing = {
        route.path  # type: ignore[attr-defined]
        for route in report_routes
        if "REPORT_VIEW" not in _codes_accepted_by(route)
    }
    assert not refusing, f"report routes REPORT_VIEW cannot open: {sorted(refusing)}"


def test_the_any_of_scope_admits_either_code_and_refuses_neither() -> None:
    """``REPORT_VIEW`` alone opens a sales report; a stranger is refused."""
    dependency = firm_any_permission_scope("SALES_VIEW", "REPORT_VIEW")
    assert dependency.dependency.permission_codes == (  # type: ignore[attr-defined]
        "SALES_VIEW",
        "REPORT_VIEW",
    )
    check = require_any_permission("SALES_VIEW", "REPORT_VIEW")
    assert check(_principal("REPORT_VIEW")).has_permission("REPORT_VIEW")
    assert check(_principal("SALES_VIEW")).has_permission("SALES_VIEW")
    with pytest.raises(AuthorizationError):
        check(_principal("CUSTOMER_VIEW"))


def test_the_any_of_scope_needs_at_least_one_code() -> None:
    """An any-of scope over nothing would open a route to everybody."""
    with pytest.raises(ValueError, match="At least one"):
        firm_any_permission_scope()
