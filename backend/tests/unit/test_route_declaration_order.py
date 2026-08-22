"""A literal path must be declared before the `/{id}` that would swallow it.

FastAPI matches routes in declaration order, so `GET /api/v1/vendors/{vendor_id}`
declared above `GET /api/v1/vendors/categories` answers the categories request
first -- and answers it 422, because "categories" is not a UUID. The endpoint is
unreachable, and nothing about it looks wrong at the call site.

It has happened nine more times than anybody knew. `sales_territories` put
`/{territory_id}` above `/dashboard`, `/search`, `/beat-plans` and `/export`,
so the Geography dashboard had never shown a number and beat plans could not be
listed at all -- that one was found by hand. Writing this test found the rest
in one run: `vendors/categories` and `vendors/types`, which is why those two
masters had no caller, and the `GET /export` of `branches`, `warehouses`,
`sales-orders`, `delivery-notes`, `goods-receipts`, `purchase-invoices` and
`purchase-returns`. Every one of them 422'd from the day it was written.

This walks the built application rather than the source, so it sees exactly
what the router will match at runtime, prefixes and all.
"""

# ruff: noqa: D103

import re
from functools import lru_cache

#: A path parameter, whatever it is called.
_PARAM = re.compile(r"^\{[^}]+\}$")


@lru_cache(maxsize=1)
def _routes() -> tuple[tuple[str, frozenset[str], int], ...]:
    """Return (path, methods, declaration index) for every route, in order."""
    from fastapi.routing import APIRoute

    from app.main import create_app

    collected: list[tuple[str, frozenset[str], int]] = []
    for index, route in enumerate(create_app().routes):
        if isinstance(route, APIRoute):
            collected.append((route.path, frozenset(route.methods), index))
            continue
        # Newer FastAPI wraps an included router; its own routes carry the
        # prefix already, so read them out rather than the wrapper.
        inner = getattr(route, "original_router", None)
        if inner is None:
            continue
        for nested in inner.routes:
            if isinstance(nested, APIRoute):
                collected.append(
                    (nested.path, frozenset(nested.methods), len(collected))
                )
    return tuple(collected)


def _shadowed() -> list[str]:
    """Return every literal route a parameterised one declared earlier hides."""
    problems: list[str] = []
    routes = _routes()
    for path, methods, index in routes:
        segments = path.strip("/").split("/")
        for other_path, other_methods, other_index in routes:
            if other_index >= index or not (methods & other_methods):
                continue
            other_segments = other_path.strip("/").split("/")
            if len(other_segments) != len(segments):
                continue
            # The earlier route hides this one when every segment either
            # matches exactly or is a parameter standing where this route has
            # a literal.
            hides = False
            for mine, theirs in zip(segments, other_segments, strict=True):
                if mine == theirs:
                    continue
                if _PARAM.match(theirs) and not _PARAM.match(mine):
                    hides = True
                    continue
                hides = False
                break
            if hides:
                problems.append(
                    f"{sorted(methods & other_methods)} {path} is hidden by "
                    f"{other_path}, declared earlier"
                )
    return problems


def test_no_literal_path_is_hidden_by_an_earlier_parameter() -> None:
    problems = _shadowed()
    assert not problems, (
        "these endpoints can never be reached -- FastAPI matches in "
        f"declaration order and answers the earlier route: {problems}. Move "
        "the literal path above the parameterised one in its router."
    )


def test_the_guard_reads_a_real_route_table() -> None:
    """A guard that inspects nothing cannot fail."""
    routes = _routes()
    assert len(routes) > 300, f"only {len(routes)} routes parsed"

    paths = {path for path, _, _ in routes}
    # The two the vendor masters needed, and the sales_territories case.
    assert "/api/v1/vendors/categories" in paths
    assert "/api/v1/sales-territories/dashboard" in paths

    ordering = {path: index for path, _, index in routes}
    assert (
        ordering["/api/v1/vendors/categories"] < ordering["/api/v1/vendors/{vendor_id}"]
    ), "the fix on 2026-08-22 was to declare the masters first"
