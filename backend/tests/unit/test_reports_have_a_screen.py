"""Every report the server can produce should be listed in the catalogue.

`test_routes_have_a_caller.py` cannot see this class. It matches a served path
against the *shapes* the desktop builds, and a hole on either side matches any
segment -- so `/api/v1/sales-returns/reports/register` looks reachable because
`/api/v1/sales-orders/reports/register` has the same five-segment shape and is
listed. Six reports were unreachable for exactly that reason: the sales
return's four and the quotation's two, all written after
`report_catalog.dart` was and never added to it, all working and returning
real rows when driven by hand.

The reports workspace is the one screen that renders a report, and it renders
what the catalogue names. So the question is not "does some path of this shape
appear in the client" but "does *this* path appear in the catalogue", and that
is a question with an exact answer.

The test skips when the desktop tree is absent, so the backend suite still
stands on its own.
"""

# ruff: noqa: D103

import re
from functools import lru_cache
from pathlib import Path

import pytest

_DESKTOP = Path(__file__).resolve().parents[3] / "desktop" / "lib"
_CATALOGUE = _DESKTOP / "ui" / "reports" / "report_catalog.dart"

#: `path: '/api/v1/sales-orders/reports/register',` in the catalogue.
_CATALOGUE_PATH = re.compile(r"path:\s*'(/api/v1/[^']+)'")

#: Reports that the server produces and the workspace deliberately does not
#: list, with the reason. A report belongs here only when another screen shows
#: it better -- not when nobody has got round to adding it.
_ELSEWHERE: dict[str, str] = {
    "/api/v1/sales-invoices/reports/summary": (
        "not a tabular report -- it answers one object of counts and totals, "
        "and the invoice workspace's own header cards read it through "
        "`documentSummary('sales-invoices', path: 'reports/summary')`. The "
        "grid here derives its columns from rows and has none to derive from."
    ),
}


@lru_cache(maxsize=1)
def _catalogued() -> frozenset[str]:
    """Every path `report_catalog.dart` names."""
    return frozenset(_CATALOGUE_PATH.findall(_CATALOGUE.read_text(encoding="utf-8")))


@lru_cache(maxsize=1)
def _report_routes() -> tuple[str, ...]:
    """Every GET the application serves under a `/reports/` segment.

    Read off the OpenAPI schema rather than the routers, which hold the
    mounted prefixes rather than their endpoints.
    """
    from app.main import create_app

    served: list[str] = []
    for path, operations in create_app().openapi()["paths"].items():
        if "/reports/" not in path:
            continue
        if "get" in operations:
            served.append(path)
    return tuple(sorted(served))


@pytest.mark.skipif(not _CATALOGUE.exists(), reason="desktop tree not present")
def test_every_report_route_is_in_the_catalogue() -> None:
    routes = _report_routes()
    assert len(routes) > 20, "the scan found almost nothing -- the shape moved"

    unlisted = sorted(set(routes) - _catalogued() - set(_ELSEWHERE))
    assert not unlisted, (
        "these reports are served and no screen can open them:\n  "
        + "\n  ".join(unlisted)
        + "\n\nAdd each to `reportCatalog` in "
        "`desktop/lib/ui/reports/report_catalog.dart`, or record it in "
        "`_ELSEWHERE` in this file with the screen that shows it better."
    )


@pytest.mark.skipif(not _CATALOGUE.exists(), reason="desktop tree not present")
def test_the_catalogue_names_no_route_that_does_not_exist() -> None:
    """The other direction: an entry pointing at nothing renders an error.

    A typo here is worse than a missing entry, because the report appears in
    the list and fails when somebody opens it.
    """
    from app.main import create_app

    served = {
        path
        for path, operations in create_app().openapi()["paths"].items()
        if "get" in operations
    }
    dangling = sorted(path for path in _catalogued() if path not in served)
    assert not dangling, (
        "the report catalogue names paths the application does not serve:\n  "
        + "\n  ".join(dangling)
    )
