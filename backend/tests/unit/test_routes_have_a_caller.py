"""Every route this platform serves should be reachable from the desktop.

The other direction is guarded by `test_desktop_calls_reach_a_route.py`: a path
the desktop builds must exist. This is the inverse, and it is the check that
row 39 of the review checklist ran by hand, did not write down, and which then
had to be reconstructed from scratch two days later to find the next thing
worth fixing.

Three features have come off the list it produces, and each had been unusable
for months without anybody noticing:

- `category_attribute_rules` -- endpoints existed, nothing called them, so from
  2026-08-15 no firm could make any product attribute mandatory.
- `vendors/categories` and `/types` -- no screen, and the routes were declared
  below `/vendors/{vendor_id}` so neither list had ever returned a row.
- `product_packaging_levels` -- full CRUD, no caller, and nothing anywhere read
  the barcodes those levels carry, so the framework doc's claim about scanning
  a carton label had no implementation behind it.

A route with no caller is not automatically a defect -- some are deliberate API
surface, some are duplicated by a better endpoint. So this does not forbid
them: it pins the ones that have been looked at and judged, and fails on a new
one. Adding a route the desktop does not call is then a deliberate act with a
reason recorded beside it, which is the same shape `_FAMILIES` takes in the
forward test.

The test skips when the desktop tree is absent, so the backend suite still
stands on its own.
"""

# ruff: noqa: D103

import re
from functools import lru_cache
from pathlib import Path

import pytest

_DESKTOP = Path(__file__).resolve().parents[3] / "desktop" / "lib"
_API_CLIENT = _DESKTOP / "core" / "api" / "api_client.dart"

#: `'/api/v1/customers/$id/notes'` in either quote style.
_PATH_LITERAL = re.compile(r"""['"](/api/v1/[^'"\s]*)['"]""")
#: An interpolation can hold quotes of its own, so it is flattened before the
#: literal is read out or the literal appears to end inside it.
_INTERPOLATION = re.compile(r"\$\{[^{}]*\}")

#: Routes deliberately left without a desktop caller, and why. Every entry has
#: been looked at; if one of these ever gains a screen, delete its line.
#:
#: These four were judged on 2026-08-23 alongside the packaging-level work that
#: came off the same audit.
_ACCEPTED: dict[str, str] = {
    "GET /api/v1/document-framework/documents/{document_id}/timeline": (
        "duplicates the per-module GET /{resource}/{id}/history, which the "
        "desktop does call and which returns the module's own shape"
    ),
    "POST /api/v1/document-framework/documents/{document_id}/events": (
        "services record timeline events themselves through `_record_event`; "
        "a client posting one by hand would write history nothing produced"
    ),
    "GET /api/v1/sales-territories/addresses/{owner_type}/{owner_id}": (
        "superseded by the per-module address forms, which read and write the "
        "six geography keys through GeoAreaPicker"
    ),
    "PUT /api/v1/sales-territories/addresses/{owner_type}/{owner_id}": (
        "superseded by the per-module address forms"
    ),
}


@lru_cache(maxsize=1)
def _served() -> tuple[tuple[str, str], ...]:
    """Every (method, path) the application serves under /api/v1.

    Read off the OpenAPI schema rather than `app.routes`, which holds the
    mounted routers rather than their endpoints.
    """
    from app.main import create_app

    served: list[tuple[str, str]] = []
    for path, operations in create_app().openapi()["paths"].items():
        if not path.startswith("/api/v1"):
            continue
        for method in operations:
            if method.upper() in {"HEAD", "OPTIONS"}:
                continue
            served.append((method.upper(), path))
    return tuple(sorted(served))


def _segments(path: str) -> tuple[str, ...]:
    """Split a route or a call, with everything variable reduced to a hole.

    A route's `{customer_id}` and a call's `$id` are both holes, and a segment
    the desktop interpolates entirely (`'/api/v1/$resource'`) is a hole too --
    which is exactly what lets one generic helper reach many resources.
    """
    path = _INTERPOLATION.sub("{}", path).split("?", 1)[0].strip("/")
    path = re.sub(r"\$[A-Za-z_][A-Za-z0-9_.]*", "{}", path)
    return tuple(
        "{}" if part.startswith("{") and part.endswith("}") else part
        for part in path.split("/")
    )


@lru_cache(maxsize=1)
def _call_shapes() -> tuple[tuple[str, ...], ...]:
    """Return the segment shape of every `/api/v1/...` literal in the desktop."""
    shapes: set[tuple[str, ...]] = set()
    for source in sorted(_DESKTOP.rglob("*.dart")):
        text = _INTERPOLATION.sub("{}", source.read_text(encoding="utf-8"))
        for match in _PATH_LITERAL.finditer(text):
            shapes.add(_segments(match.group(1)))
    return tuple(sorted(shapes))


def _is_reachable(path: str) -> bool:
    """Report whether some path the desktop builds could resolve to this route.

    A hole on the *call* side matches any segment, because that is what a
    generic helper such as `documentAction` does. A hole on the route side
    matches a hole or whatever the caller filled in.
    """
    route = _segments(path)
    for shape in _call_shapes():
        if len(shape) != len(route):
            continue
        if all(
            call == "{}" or part == "{}" or call == part
            for call, part in zip(shape, route, strict=True)
        ):
            return True
    return False


@pytest.mark.skipif(not _API_CLIENT.exists(), reason="desktop tree not present")
def test_every_route_is_reachable_or_accepted() -> None:
    orphans = {
        f"{method} {path}" for method, path in _served() if not _is_reachable(path)
    }
    assert len(_call_shapes()) > 100, "the scan found almost nothing -- shape moved"

    unexplained = sorted(orphans - set(_ACCEPTED))
    assert not unexplained, (
        "these routes are served and nothing in the desktop can reach them:\n  "
        + "\n  ".join(unexplained)
        + "\n\nEither give them a caller, or add each to `_ACCEPTED` in this "
        "file with the reason it does not need one."
    )


@pytest.mark.skipif(not _API_CLIENT.exists(), reason="desktop tree not present")
def test_the_accepted_list_holds_nothing_that_gained_a_caller() -> None:
    """A stale exception is how a list like this stops meaning anything.

    If one of these gains a screen, the entry has to go -- otherwise the next
    person reads it as a considered decision about today's code.
    """
    orphans = {
        f"{method} {path}" for method, path in _served() if not _is_reachable(path)
    }

    stale = sorted(set(_ACCEPTED) - orphans)
    assert not stale, (
        "these are listed as having no caller and now have one:\n  "
        + "\n  ".join(stale)
        + "\n\nRemove them from `_ACCEPTED`."
    )
