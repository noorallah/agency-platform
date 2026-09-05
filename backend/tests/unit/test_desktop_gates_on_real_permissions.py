"""A permission the desktop gates on must be one the platform actually seeds.

`module_catalog.dart` decides what a signed-in user is offered, by naming
permission codes. Nothing checked that those codes exist.

A typo is silent and permanent: `requiredPermissions: ['CUSTOMR_VIEW']` hides
that module from **every** non-platform-admin user for ever, with no error
anywhere -- the filter simply never matches, and a missing module looks like a
product decision rather than a defect. A code that is seeded but attached to
no role fails the same way for everybody except a platform admin, who passes
every check by short-circuit and would never see it.

`test_identity_hardening.py` guards the other direction -- every code the
**backend** enforces is seeded -- by scanning `app/`. It never reads Dart, so
the desktop side was unguarded in both respects.

The codes live in Dart and the catalogue lives in Python, so one side has to
read the other's source. Reading it with a regex is coarse; the alternative is
a second copy of the list, which is the thing that lets two files drift apart
to begin with. `test_search_navigation_targets.py` already parses this same
file for tab ids and takes the same trade.

Skips rather than fails when the desktop tree is absent, so the backend suite
still stands on its own.
"""

# ruff: noqa: D103

import re
from functools import lru_cache
from pathlib import Path

import pytest

from app.identity.system_seed import ROLE_PERMISSION_CODES, SYSTEM_PERMISSION_CODES

_CATALOG = (
    Path(__file__).resolve().parents[3]
    / "desktop"
    / "lib"
    / "ui"
    / "workspace"
    / "module_catalog.dart"
)

#: `requiredPermissions: ['CUSTOMER_VIEW', 'CUSTOMER_CREATE'],` on a module or
#: a tab, however the formatter has wrapped it.
_REQUIRED = re.compile(r"requiredPermissions:\s*(?:const\s*)?\[(.*?)\]", re.S)
#: An upper-snake code inside such a list. Deliberately not `[A-Z_]+`: a
#: lowercase code would be a different bug and is caught by the naming guard
#: on the backend side.
_CODE = re.compile(r"'([A-Z][A-Z0-9_]{2,})'")


@lru_cache(maxsize=1)
def _gated_codes() -> frozenset[str]:
    """Every permission code the desktop's module catalogue gates on."""
    source = _CATALOG.read_text(encoding="utf-8")
    codes: set[str] = set()
    for block in _REQUIRED.findall(source):
        codes.update(_CODE.findall(block))
    return frozenset(codes)


@pytest.mark.skipif(not _CATALOG.exists(), reason="desktop tree not present")
def test_every_code_the_desktop_gates_on_is_seeded() -> None:
    gated = _gated_codes()
    assert len(gated) > 40, (
        "the scan found almost nothing -- `requiredPermissions:` moved, and "
        "this guard is now checking an empty set"
    )
    unknown = sorted(gated - set(SYSTEM_PERMISSION_CODES))
    assert not unknown, (
        "`module_catalog.dart` gates on permission codes the platform does "
        "not seed:\n  "
        + "\n  ".join(unknown)
        + "\n\nA code that is never seeded matches nothing, so the module or "
        "tab is hidden from every user who is not a platform administrator, "
        "silently and for ever. Fix the spelling, or add the code to "
        "`PERMISSION_GROUPS` in `app/identity/system_seed.py`."
    )


@pytest.mark.skipif(not _CATALOG.exists(), reason="desktop tree not present")
def test_every_code_the_desktop_gates_on_reaches_some_role() -> None:
    """A seeded code held by nobody hides the screen just as thoroughly.

    Separate from the test above because the failures want different fixes:
    an unseeded code is a typo in the Dart, where an ungranted one is a
    decision missing from `ROLE_PERMISSION_CODES`.
    """
    granted: set[str] = set()
    for codes in ROLE_PERMISSION_CODES.values():
        granted.update(codes)
    orphaned = sorted(_gated_codes() - granted)
    assert not orphaned, (
        "`module_catalog.dart` gates on codes no system role holds:\n  "
        + "\n  ".join(orphaned)
        + "\n\nOnly a platform administrator would ever see these, because "
        "they pass every permission check by short-circuit rather than by "
        "holding a code. Grant them to a role in "
        "`app/identity/system_seed.py`, or gate the screen on something a "
        "user can actually be given."
    )
