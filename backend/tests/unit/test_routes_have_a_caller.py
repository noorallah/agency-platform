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

#: Reasons shared by many pinned routes (D-GOLIVE-2 triage, 2026-10-01).
_API_SURFACE = (
    "scripted migration and integration surface: a JSON batch, all or "
    "nothing; the screens bring opening balances from files (`import-file`, "
    "§36), and history stays in the old tool (§56 B)"
)
_MACHINE_EXPORT = (
    "machine export for integrations; the desktop's lists export what they "
    "show from the grid"
)
_SCREEN_GAP = "a screen gap, recorded in docs/BACKLOG.md §76 (D-GOLIVE-2 triage)"

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
    "POST /api/v1/customers/import": _API_SURFACE,
    "POST /api/v1/vendors/import": _API_SURFACE,
    "POST /api/v1/products/import": _API_SURFACE,
    "POST /api/v1/customers/opening-bills/import": _API_SURFACE,
    "POST /api/v1/vendors/opening-bills/import": _API_SURFACE,
    "POST /api/v1/inventory/opening-stock/import": _API_SURFACE,
    "POST /api/v1/delivery-notes/import": _API_SURFACE,
    "POST /api/v1/goods-receipts/import": _API_SURFACE,
    "POST /api/v1/purchase-invoices/import": _API_SURFACE,
    "POST /api/v1/purchase-returns/import": _API_SURFACE,
    "POST /api/v1/quotations/import": _API_SURFACE,
    "POST /api/v1/sales-invoices/import": _API_SURFACE,
    "POST /api/v1/sales-orders/import": _API_SURFACE,
    "POST /api/v1/sales-returns/import": _API_SURFACE,
    "POST /api/v1/tax-framework/legacy/import-csv": _API_SURFACE,
    "POST /api/v1/tax-framework/rules/import": _API_SURFACE,
    "POST /api/v1/tax-framework/systems/import": _API_SURFACE,
    "GET /api/v1/delivery-notes/export": _MACHINE_EXPORT,
    "GET /api/v1/goods-receipts/export": _MACHINE_EXPORT,
    "GET /api/v1/purchase-invoices/export": _MACHINE_EXPORT,
    "GET /api/v1/purchase-returns/export": _MACHINE_EXPORT,
    "GET /api/v1/quotations/export": _MACHINE_EXPORT,
    "GET /api/v1/sales-invoices/export/csv": _MACHINE_EXPORT,
    "GET /api/v1/sales-orders/export": _MACHINE_EXPORT,
    "GET /api/v1/sales-returns/export": _MACHINE_EXPORT,
    "GET /api/v1/tax-framework/rules/export": _MACHINE_EXPORT,
    "GET /api/v1/tax-framework/systems/export": _MACHINE_EXPORT,
    "GET /api/v1/finance/account-summaries": (
        "superseded by the trial balance, which answers the same per-account "
        "balances with opening and movement"
    ),
    "POST /api/v1/uom-framework/convert": (
        "every document converts on the server through `convert_quantity`; "
        "a client never asks"
    ),
    "POST /api/v1/branches/bulk-status": _SCREEN_GAP,
    "POST /api/v1/warehouses/bulk-status": _SCREEN_GAP,
    "POST /api/v1/vendors/bulk-status": _SCREEN_GAP,
    "POST /api/v1/vendors/bulk-category": _SCREEN_GAP,
    "POST /api/v1/vendors/bulk-profile": _SCREEN_GAP,
    "POST /api/v1/tax-framework/components/bulk-delete": _SCREEN_GAP,
    "POST /api/v1/tax-framework/components/bulk-restore": _SCREEN_GAP,
    "POST /api/v1/tax-framework/profiles/bulk-delete": _SCREEN_GAP,
    "POST /api/v1/tax-framework/profiles/bulk-restore": _SCREEN_GAP,
    "POST /api/v1/tax-framework/profiles/bulk-status": _SCREEN_GAP,
    "POST /api/v1/tax-framework/systems/bulk-delete": _SCREEN_GAP,
    "POST /api/v1/tax-framework/systems/bulk-restore": _SCREEN_GAP,
    "GET /api/v1/document-framework/document-states": _SCREEN_GAP,
    "POST /api/v1/document-framework/document-states": _SCREEN_GAP,
    "PUT /api/v1/document-framework/document-states/{state_id}": _SCREEN_GAP,
    "DELETE /api/v1/document-framework/document-states/{state_id}": _SCREEN_GAP,
    "PUT /api/v1/document-framework/document-types/{document_type_id}": _SCREEN_GAP,
    "DELETE /api/v1/document-framework/document-types/{document_type_id}": _SCREEN_GAP,
    "PATCH /api/v1/finance/financial-years/{year_id}": _SCREEN_GAP,
    "DELETE /api/v1/finance/financial-years/{year_id}": _SCREEN_GAP,
    "GET /api/v1/branch-warehouse/settings": _SCREEN_GAP,
    "GET /api/v1/sales-returns/summary": _SCREEN_GAP,
    # Requests for quotation (PG-8): the server half merged first; desktop in
    # PG-8 part 2, which takes these entries out again.
    "GET /api/v1/rfqs": "desktop in PG-8 part 2",
    "POST /api/v1/rfqs": "desktop in PG-8 part 2",
    "POST /api/v1/rfqs/from-requisition/{requisition_id}": "desktop in PG-8 part 2",
    "GET /api/v1/rfqs/{rfq_id}": "desktop in PG-8 part 2",
    "PUT /api/v1/rfqs/{rfq_id}": "desktop in PG-8 part 2",
    "POST /api/v1/rfqs/{rfq_id}/send": "desktop in PG-8 part 2",
    "POST /api/v1/rfqs/{rfq_id}/cancel": "desktop in PG-8 part 2",
    "POST /api/v1/rfqs/{rfq_id}/close": "desktop in PG-8 part 2",
    "GET /api/v1/rfqs/{rfq_id}/quotations": "desktop in PG-8 part 2",
    "PUT /api/v1/rfqs/{rfq_id}/quotations/{vendor_id}": "desktop in PG-8 part 2",
    "GET /api/v1/rfqs/{rfq_id}/comparison": "desktop in PG-8 part 2",
    "PUT /api/v1/rfqs/{rfq_id}/selections": "desktop in PG-8 part 2",
    "POST /api/v1/rfqs/{rfq_id}/raise-orders": "desktop in PG-8 part 2",
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


#: A call segment filled from a variable named like an id: it names one
#: record, so it can stand only where the route has a placeholder -- never for
#: a literal like `opening-bills` (D-GOLIVE-2).
_ID_VARIABLE = re.compile(r"^(id|[A-Za-z_]*Id|[a-z_]*_id)$")
#: A desktop string literal that may be a resource name a generic helper is
#: handed (`'vendors/categories'`, `'sales-returns'`).
_RESOURCE_LITERAL = re.compile(r"'([a-z][a-z0-9-]*(?:/[a-z0-9-]+)*)'")
#: The literal `path:` arguments the summary helper is called with.
_PATH_ARGUMENT = re.compile(r"path: '([a-z/-]+)'")
#: Matches one segment or several: a generic `$resource` may be
#: `vendors/categories`.
_ANY = r"[^/]+(?:/[^/]+)*"
#: A route placeholder, as the route side is written for matching.
_HOLE = "\x00"


def _call_pattern(path: str) -> re.Pattern[str]:
    """Turn one desktop path literal into a pattern over route paths.

    An id-named variable matches only a route placeholder; any other
    variable or interpolation matches one or more segments of anything.
    """
    parts: list[str] = []
    for segment in path.split("?", 1)[0].strip("/").split("/"):
        if "${" in segment:
            parts.append(_ANY)
            continue
        if segment.startswith("$"):
            matched = re.match(r"\$([A-Za-z_][A-Za-z0-9_]*)", segment)
            name = matched.group(1) if matched else ""
            rest = segment[len(name) + 1 :]
            if _ID_VARIABLE.match(name) and not rest:
                parts.append(_HOLE)
            else:
                parts.append(_ANY + re.escape(rest))
            continue
        parts.append(re.escape(segment))
    return re.compile("^" + "/".join(parts) + "$")


def _is_generic(path: str) -> bool:
    """Say whether a literal has no fixed segment after `/api/v1/`."""
    segments = path.split("?", 1)[0].strip("/").split("/")[2:]
    return all(seg.startswith("$") or "${" in seg for seg in segments)


@lru_cache(maxsize=1)
def _call_patterns() -> tuple[re.Pattern[str], ...]:
    """Return a pattern for every path the desktop can build.

    A fully generic helper -- `'/api/v1/$resource/$id'` -- could reach any
    route at all, which is how two unscreened routes passed this guard
    (D-GOLIVE-2). So it is not taken as written: it is expanded with every
    resource name the desktop actually hands such helpers (string literals
    that are the prefix of a real route) and with the literal `path:`
    arguments, and only those count.
    """
    sources = [
        source.read_text(encoding="utf-8")
        for source in sorted(_DESKTOP.rglob("*.dart"))
    ]
    literals: set[str] = set()
    for text in sources:
        # Flattened first: an interpolation can hold quotes of its own, and
        # the literal would appear to end inside it.
        flat = _INTERPOLATION.sub("${x}", text)
        literals |= {match.group(1) for match in _PATH_LITERAL.finditer(flat)}
    prefixes = {path[len("/api/v1/") :] for _, path in _served()}
    # A model names a route's segment to describe data, never to call it:
    # `'sales-returns'` as an e-invoice note kind once made every
    # `/sales-returns/<helper path>` look reachable.
    callers = [
        source.read_text(encoding="utf-8")
        for source in sorted(_DESKTOP.rglob("*.dart"))
        if "models" not in source.relative_to(_DESKTOP).parts
    ]
    resources = sorted(
        {
            literal
            for text in callers
            for literal in _RESOURCE_LITERAL.findall(text)
            if any(p == literal or p.startswith(literal + "/") for p in prefixes)
        }
    )
    paths = {"summary"} | {
        argument for text in sources for argument in _PATH_ARGUMENT.findall(text)
    }
    templates: list[str] = []
    for resource in resources:
        templates += [
            f"/api/v1/{resource}",
            f"/api/v1/{resource}/$id",
            f"/api/v1/{resource}/$id/${{action}}",
            *(f"/api/v1/{resource}/{path}" for path in sorted(paths)),
        ]
    return tuple(
        _call_pattern(path)
        for path in [*sorted(p for p in literals if not _is_generic(p)), *templates]
    )


def _is_reachable(path: str) -> bool:
    """Report whether some path the desktop builds could resolve to this route."""
    route = "/".join(
        _HOLE if part.startswith("{") else part for part in path.strip("/").split("/")
    )
    return any(pattern.match(route) for pattern in _call_patterns())


@pytest.mark.skipif(not _API_CLIENT.exists(), reason="desktop tree not present")
def test_every_route_is_reachable_or_accepted() -> None:
    orphans = {
        f"{method} {path}" for method, path in _served() if not _is_reachable(path)
    }
    assert len(_call_patterns()) > 100, "the scan found almost nothing -- shape moved"

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
