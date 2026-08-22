"""Every path the desktop builds must be one this application serves.

Nothing checked this, and on 2026-08-22 it cost a working button. The finance
workspace renders one `SettlementsPage` for receipts, payments and refunds, and
that page offers **Reverse** on every row -- but only receipts and payments had
`POST /api/v1/{resource}/{id}/reverse`. The refunds screen answered 405, and no
test on either side could see it: the desktop's fake API returns whatever the
test wants, and the backend suite never hears of the desktop.

Two shapes are checked here, because the defect lived in the second.

**Literal paths.** A path written out in full is compared against the route
table. Paths whose *first* segment is interpolated -- `'/api/v1/$resource'` and
friends -- cannot be resolved from the text, and there are a handful of generic
helpers built exactly that way; those are skipped, and the count is asserted so
a new one is a deliberate act rather than a hole that quietly widens.

**Enum-rooted families.** `'/api/v1/${direction.path}/$id/reverse'` is three
paths, one per member of a Dart enum, and it is the shape that broke: the
template resolved for two members and not the third. The members are read out
of the Dart rather than restated here, so adding a fourth settlement direction
fails this test until its routes exist.

The tests skip rather than fail when the desktop tree is absent, so the backend
suite still stands on its own.
"""

# ruff: noqa: D103

import re
from functools import lru_cache
from pathlib import Path

import pytest

_DESKTOP = Path(__file__).resolve().parents[3] / "desktop" / "lib"
_API_CLIENT = _DESKTOP / "core" / "api" / "api_client.dart"
_SETTLEMENT_DIRECTION = _DESKTOP / "models" / "settlement_direction.dart"
_GEOGRAPHY = _DESKTOP / "models" / "geography.dart"

#: `'/api/v1/customers/$id/notes'` in either quote style.
_PATH_LITERAL = re.compile(r"""['"](/api/v1/[^'"\s]*)['"]""")
#: `${action.startsWith('/') ? ... }` -- an interpolation can hold quotes of
#: its own, so it is flattened before the literal is read out or the literal
#: appears to end inside it.
_INTERPOLATION = re.compile(r"\$\{[^{}]*\}")
#: `path: 'countries',` inside an enum member.
_ENUM_PATH = re.compile(r"path:\s*'([a-z-]+)'")
#: `SettlementDirection.receipt => 'receipts',`
_SWITCH_PATH = re.compile(r"=>\s*'([a-z-]+)',")

#: Paths a variable fills in, which no amount of reading the text can resolve.
#: Six are the generic resource-taking helpers -- `documentPage`, `create`,
#: `update`, `documentAction` and their siblings -- and four are families whose
#: leaf is chosen at runtime, each covered by a test of its own below. The list
#: is written out rather than counted so that a new one is a deliberate act:
#: an unchecked family is where the refunds defect lived.
_FAMILIES = {
    "/api/v1/{}": "documentPage / create / _list",
    "/api/v1/{}/{}": "documentDetail / update / delete",
    "/api/v1/{}/{}/{}": "documentAction",
    "/api/v1/{}/{}/history": "documentHistory",
    "/api/v1/{}/{}/reverse": "settlements -- see the direction test",
    "/api/v1/{}/outstanding": "settlements -- see the direction test",
    "/api/v1/sales-territories/geo/{}": "geography -- see the level test",
    "/api/v1/sales-territories/geo/{}/{}": "geography -- see the level test",
    "/api/v1/quotations/{}/{}": "quotation lifecycle -- see the action test",
    "/api/v1/sales-returns/{}/{}": "sales return lifecycle -- see the action test",
}


@lru_cache(maxsize=1)
def _routes() -> frozenset[str]:
    """Every served path, with its parameters flattened to `{}`.

    Cached: building the application is the slow part of this file, and the
    route table does not change between tests.
    """
    from app.main import create_app

    return frozenset(
        re.sub(r"\{[^}]*\}", "{}", path) for path in create_app().openapi()["paths"]
    )


def _normalise(path: str) -> str:
    """Turn a Dart path literal into the shape a route template has.

    `'/api/v1/customers/$id/notes?page=1'` becomes `/api/v1/customers/{}/notes`.
    """
    path = _INTERPOLATION.sub("{}", path).split("?", 1)[0].rstrip("/")
    return re.sub(r"\$[A-Za-z_][A-Za-z0-9_.]*", "{}", path)


def _literals() -> dict[str, set[str]]:
    """Every `/api/v1/...` literal in the desktop, by normalised path."""
    found: dict[str, set[str]] = {}
    for source in sorted(_DESKTOP.rglob("*.dart")):
        text = _INTERPOLATION.sub("{}", source.read_text(encoding="utf-8"))
        for match in _PATH_LITERAL.finditer(text):
            found.setdefault(_normalise(match.group(1)), set()).add(source.name)
    return found


def _enum_values(source: Path) -> list[str]:
    """Return the path segments a Dart enum's members carry.

    Two spellings: a `path:` field on each member, or a `String get path`
    switch. The switch is read from its own block rather than the whole file,
    which holds other switches over the same enum -- reading them all returned
    the party parameter names beside the paths.
    """
    text = source.read_text(encoding="utf-8")
    values = _ENUM_PATH.findall(text)
    if values:
        return values
    head = text.split("String get path", 1)
    if len(head) == 1:
        return []
    return _SWITCH_PATH.findall(head[1].split("};", 1)[0])


@pytest.mark.skipif(not _API_CLIENT.exists(), reason="desktop tree not present")
def test_every_literal_path_the_desktop_writes_is_served() -> None:
    routes = _routes()
    literals = _literals()
    assert len(literals) > 150, "the scan found almost nothing -- the shape moved"

    unknown = {
        path: sorted(origins)
        for path, origins in literals.items()
        if path not in routes and path not in _FAMILIES
    }
    assert not unknown, (
        "the desktop builds these and no route answers them, so the screen "
        f"that calls one gets a 404: {unknown}"
    )

    unlisted = {path for path in literals if path not in routes and path in _FAMILIES}
    assert unlisted == set(_FAMILIES), (
        "a family in the list is no longer built by the desktop, or the list "
        f"has drifted: built {sorted(unlisted)}, listed {sorted(_FAMILIES)}"
    )


@pytest.mark.skipif(
    not _SETTLEMENT_DIRECTION.exists(), reason="desktop tree not present"
)
def test_every_settlement_direction_can_do_what_the_screen_offers() -> None:
    """The defect this file was written for.

    One page serves all three directions, so an operation missing for one of
    them is a button that fails on one screen out of three. `outstanding` is
    the exception and is asked for only where the dialog allocates -- a refund
    hands back money held on account and is not applied to an invoice.
    """
    directions = _enum_values(_SETTLEMENT_DIRECTION)
    assert set(directions) == {"receipts", "payments", "refunds"}, directions

    routes = _routes()
    missing: list[str] = []
    for direction in directions:
        expected = [
            f"/api/v1/{direction}",
            f"/api/v1/{direction}/{{}}",
            f"/api/v1/{direction}/{{}}/reverse",
        ]
        if direction != "refunds":
            expected.append(f"/api/v1/{direction}/outstanding")
        missing += [path for path in expected if path not in routes]
    assert not missing, (
        "the settlements screen offers these for every direction and the "
        f"backend serves them for some: {missing}"
    )


@pytest.mark.skipif(not _GEOGRAPHY.exists(), reason="desktop tree not present")
def test_every_geography_level_can_be_managed() -> None:
    """The picker walks six levels; each needs the same four routes behind it."""
    levels = _enum_values(_GEOGRAPHY)
    assert len(levels) == 6, levels

    routes = _routes()
    missing = [
        path
        for level in levels
        for path in (
            f"/api/v1/sales-territories/geo/{level}",
            f"/api/v1/sales-territories/geo/{level}/{{}}",
        )
        if path not in routes
    ]
    assert not missing, f"a geography level with no route behind it: {missing}"


@pytest.mark.skipif(not _API_CLIENT.exists(), reason="desktop tree not present")
def test_every_document_action_a_screen_offers_has_a_route() -> None:
    """The lifecycle buttons, which reach their endpoint by suffix.

    Each of these pages holds the action names in its own toolbar rather than
    in the client, so the button and the route can drift apart without either
    side noticing -- the same shape as the refunds Reverse.
    """
    routes = _routes()
    offered = {
        "quotations": ("send", "accept", "decline", "cancel", "convert"),
        "sales-returns": ("approve", "complete", "close", "cancel"),
        "delivery-notes": ("approve", "dispatch", "complete", "close", "cancel"),
        "sales-orders": ("approve", "cancel", "close"),
        "sales-invoices": ("approve", "cancel", "close"),
        "purchase-invoices": ("approve", "cancel", "close"),
        "purchase-returns": ("approve", "complete", "close", "cancel"),
    }
    missing = [
        f"/api/v1/{resource}/{{}}/{action}"
        for resource, actions in offered.items()
        for action in actions
        if f"/api/v1/{resource}/{{}}/{action}" not in routes
    ]
    assert not missing, f"a toolbar button with no endpoint behind it: {missing}"


def test_the_guard_notices_a_path_nothing_serves() -> None:
    """A guard that cannot fail is not a guard."""
    assert _normalise("/api/v1/customers/$id/notes?page=1") == (
        "/api/v1/customers/{}/notes"
    )
    assert _normalise("/api/v1/${direction.path}/$id/reverse") == (
        "/api/v1/{}/{}/reverse"
    )

    routes = _routes()
    assert "/api/v1/receipts/{}/reverse" in routes
    assert "/api/v1/refunds/{}/reverse" in routes, (
        "the refund reversal added on 2026-08-22 -- if this is gone, the "
        "Reverse button on the refunds screen is answering 405 again"
    )
    assert "/api/v1/refunds/{}/unreverse" not in routes
