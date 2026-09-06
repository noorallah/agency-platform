"""A seeded role must be able to open at least one module, with at least one tab.

`CASHIER` holds `RECEIPT_CREATE`, `RECEIPT_VIEW`, `PAYMENT_CREATE` and
`PAYMENT_VIEW`. Receipts and Payments are tabs of **Finance**, which was gated
on `ACCOUNT_VIEW`, and the tabs named no codes of their own so they inherited
it. A cashier therefore signed in to an **empty sidebar** -- a working account,
correct permissions, and nothing on screen.

Nobody hit it because the seeded `counter-sales` template pairs `CASHIER` with
`BILLING_EXECUTIVE`, which is offered six modules. A cashier on their own was
not something anybody had made.

This asks the question of every seeded firm role rather than of the one that
was reported: which modules is this role offered, and does at least one of them
have a tab it can open? A module offered with no openable tab is the same
failure one level down -- it opens empty -- and `FIRM_ADMIN` has one, recorded
in `_MODULES_THAT_OPEN_EMPTY` below.

It parses `module_catalog.dart`, as `test_desktop_gates_on_real_permissions.py`
and `test_search_navigation_targets.py` already do. The alternative is a second
copy of the catalogue in Python, which is the thing that lets two files drift.
"""

# ruff: noqa: D103

import re
from functools import lru_cache
from pathlib import Path

import pytest

from app.identity.system_seed import ROLE_PERMISSION_CODES, SYSTEM_ROLE_CODES

_CATALOG = (
    Path(__file__).resolve().parents[3]
    / "desktop"
    / "lib"
    / "ui"
    / "workspace"
    / "module_catalog.dart"
)

#: Roles that administer the platform rather than work in a firm. They are
#: granted every code or a handful of platform ones, and the modules they are
#: offered are decided by the designation rather than by this catalogue.
_PLATFORM_ROLES = frozenset(
    {"PLATFORM_ADMIN", "SUPPORT_ADMIN", "LICENSE_ADMIN", "SYSTEM_AUDITOR"}
)

#: A module a role is offered but whose every tab it is refused, recorded
#: rather than fixed. Each would be a question for whoever owns the seed.
#:
#: Empty as of 2026-09-06. `FIRM_ADMIN` + Settings was the one entry: the
#: module is offered on any of `SETTINGS_VIEW`, `AUDIT_LOG_VIEW` or
#: `DIAGNOSTICS_VIEW` and both tabs demand one of the latter two, so a firm
#: administrator holding only the first was offered the module and refused
#: every tab in it. `20260906_0131` granted `AUDIT_LOG_VIEW`, which opens the
#: Audit Logs tab on **their own firm's** trail -- `audit_scope` reads one
#: trail chosen by firm context. `DIAGNOSTICS_VIEW` stays out, so Diagnostics
#: is still theirs to be refused, and the module is no longer empty.
_MODULES_THAT_OPEN_EMPTY: frozenset[tuple[str, str]] = frozenset()


#: Tabs on a firm-reachable module that **no** seeded firm role can open.
#:
#: Each is deliberate: the business-profile catalogue, the document framework
#: and the shared geography masters are platform administration that happens
#: to live under Administration rather than behind `requiresPlatformAdmin`.
#:
#: `user-firms` was on this list and should not have been. It demanded
#: `FIRM_VIEW`, a platform code `FIRM_ADMIN` can never hold, so the one screen
#: whose whole job is assigning people to firms was invisible to the one role
#: whose job that is. Worse, #249 fixed the *definition's* `canUseAction` and
#: left the catalogue entry alone -- two gates on one screen, one of them
#: moved, and the screen still unreachable. This list exists so the next such
#: tab fails the build instead of waiting to be noticed on somebody's screen.
_TABS_NO_FIRM_ROLE_CAN_OPEN = frozenset(
    {
        # All six are the business-profile framework, gated on `PLATFORM_VIEW`
        # -- which industries exist, which features and modules they carry,
        # and which profile a firm is assigned. That is platform
        # administration that happens to live under Administration rather
        # than behind `requiresPlatformAdmin`, so a firm administrator is
        # correctly refused. `Profile Assignment` additionally asks for
        # `FIRM_VIEW`.
        "Business Profiles",
        "Feature Management",
        "Module Configuration",
        "Attribute Definitions",
        "Mandatory Attributes",
        "Profile Assignment",
    }
)


@lru_cache(maxsize=1)
def _modules() -> tuple[tuple[str, frozenset[str], bool, bool, tuple], ...]:
    """Return (label, codes, any_of, platform_only, tabs) for every module."""
    source = _CATALOG.read_text(encoding="utf-8")
    parsed = []
    for block in re.split(r"\n    ModuleDefinition\(", source)[1:]:
        label = re.search(r"label: '([^']+)'", block)
        gate = re.search(r"requiredPermissions: (?:const )?\[(.*?)\]", block, re.S)
        if label is None or gate is None:
            continue
        codes = frozenset(re.findall(r"'([A-Z][A-Z0-9_]{2,})'", gate.group(1)))
        any_of = "requiresAnyPermission: true" in block
        tabs = []
        for tab in re.findall(r"ModuleTabDefinition\((.*?)\),\n", block, re.S):
            tab_label = re.search(r"label: '([^']+)'", tab)
            tab_gate = re.search(
                r"requiredPermissions: (?:const )?\[(.*?)\]", tab, re.S
            )
            if tab_label is None:
                continue
            if tab_gate is None:
                # A tab naming no codes inherits the module's list and flag.
                tabs.append((tab_label.group(1), codes, any_of))
            else:
                tabs.append(
                    (
                        tab_label.group(1),
                        frozenset(
                            re.findall(r"'([A-Z][A-Z0-9_]{2,})'", tab_gate.group(1))
                        ),
                        "requiresAnyPermission: true" in tab,
                    )
                )
        parsed.append(
            (
                label.group(1),
                codes,
                any_of,
                "requiresPlatformAdmin: true" in block,
                tuple(tabs),
            )
        )
    return tuple(parsed)


def _passes(codes: frozenset[str], any_of: bool, held: frozenset[str]) -> bool:
    """Whether a holder of `held` passes this gate."""
    if not codes:
        return True
    return bool(codes & held) if any_of else codes <= held


_FIRM_ROLES = [role for role in SYSTEM_ROLE_CODES if role not in _PLATFORM_ROLES]


@pytest.mark.skipif(not _CATALOG.exists(), reason="desktop tree not present")
def test_the_catalogue_parsed() -> None:
    """A guard on the guard: a rename here quietly checks nothing."""
    assert len(_modules()) > 15
    assert sum(len(module[4]) for module in _modules()) > 60


@pytest.mark.skipif(not _CATALOG.exists(), reason="desktop tree not present")
@pytest.mark.parametrize("role", _FIRM_ROLES)
def test_every_firm_role_is_offered_a_module(role: str) -> None:
    held = ROLE_PERMISSION_CODES[role]
    offered = [
        label
        for label, codes, any_of, platform_only, _ in _modules()
        if not platform_only and _passes(codes, any_of, held)
    ]

    assert offered, (
        f"`{role}` is offered no module at all -- a working account with "
        "correct permissions and an empty sidebar.\n\n"
        "Gate a module on a code this role holds, and give that module's tabs "
        "codes of their own so widening the module does not widen every tab "
        "inside it. Finance is the worked example: it takes any of "
        "`ACCOUNT_VIEW`, `RECEIPT_VIEW` or `PAYMENT_VIEW`, and a cashier sees "
        "Receipts and Payments and not the chart of accounts."
    )


@pytest.mark.skipif(not _CATALOG.exists(), reason="desktop tree not present")
@pytest.mark.parametrize("role", _FIRM_ROLES)
def test_a_module_a_role_is_offered_has_a_tab_it_can_open(role: str) -> None:
    """A module that opens empty is the same failure one level down."""
    held = ROLE_PERMISSION_CODES[role]
    empty = {
        label
        for label, codes, any_of, platform_only, tabs in _modules()
        if not platform_only
        and _passes(codes, any_of, held)
        and tabs
        and not any(_passes(tc, ta, held) for _, tc, ta in tabs)
    }
    unexpected = sorted(
        label for label in empty if (role, label) not in _MODULES_THAT_OPEN_EMPTY
    )

    assert not unexpected, (
        f"`{role}` is offered these modules and refused every tab in them, so "
        f"they open empty: {', '.join(unexpected)}.\n\n"
        "Either gate the module on something this role does not hold, or give "
        "it a tab the role can open. If it is deliberate, add it to "
        "`_MODULES_THAT_OPEN_EMPTY` with the reason."
    )


@pytest.mark.skipif(not _CATALOG.exists(), reason="desktop tree not present")
def test_a_cashier_sees_the_till_and_not_the_ledger() -> None:
    """The named regression, and the half that matters.

    Widening Finance's gate without gating its tabs would have fixed the empty
    sidebar by handing a cashier the chart of accounts and the journal.
    """
    held = ROLE_PERMISSION_CODES["CASHIER"]
    finance = next(module for module in _modules() if module[0] == "Finance")
    openable = {
        label for label, codes, any_of in finance[4] if _passes(codes, any_of, held)
    }

    assert openable == {"Receipts", "Payments"}


@pytest.mark.skipif(not _CATALOG.exists(), reason="desktop tree not present")
@pytest.mark.parametrize("role", ["ACCOUNTANT", "FIRM_ADMIN", "VIEWER"])
def test_nobody_lost_a_finance_tab(role: str) -> None:
    """Gating the tabs individually must not take one away.

    Everyone who held `ACCOUNT_VIEW` saw all nine by inheritance. Every code
    now on a tab is one they already hold, so all nine survive -- checked
    rather than assumed, because this is the direction a widening breaks in.
    """
    held = ROLE_PERMISSION_CODES[role]
    finance = next(module for module in _modules() if module[0] == "Finance")
    openable = [
        label for label, codes, any_of in finance[4] if _passes(codes, any_of, held)
    ]

    assert len(openable) == len(finance[4])


@pytest.mark.skipif(not _CATALOG.exists(), reason="desktop tree not present")
def test_no_tab_is_closed_to_every_firm_role() -> None:
    """A tab nobody in a firm can open is a screen that will never be seen.

    The module-level check above passes as long as *some* tab opens, so a
    single dead tab hides inside a module full of live ones. That is exactly
    where `user-firms` sat: Administration was reachable, eleven of its tabs
    worked, and the twelfth -- the one for assigning people to firms -- asked
    for a platform code and was invisible to every firm administrator.

    When this fails, either gate the tab on something a firm role holds, or
    add it to `_TABS_NO_FIRM_ROLE_CAN_OPEN` with the reason.
    """
    firm_roles = {
        role: ROLE_PERMISSION_CODES[role]
        for role in SYSTEM_ROLE_CODES
        if role not in _PLATFORM_ROLES
    }
    closed: set[str] = set()
    for _label, _codes, _any_of, platform_only, tabs in _modules():
        if platform_only:
            continue
        for tab_label, tab_codes, tab_any in tabs:
            if not any(
                _passes(tab_codes, tab_any, held) for held in firm_roles.values()
            ):
                closed.add(tab_label)
    unexpected = sorted(closed - _TABS_NO_FIRM_ROLE_CAN_OPEN)

    assert not unexpected, (
        "no seeded firm role can open these tabs, so nobody in a firm will "
        "ever see them:\n  "
        + "\n  ".join(unexpected)
        + "\n\nGate the tab on a code a firm role holds, or record it in "
        "`_TABS_NO_FIRM_ROLE_CAN_OPEN` with the reason. Note there are **two** "
        "gates per tab -- `requiredPermissions` in `module_catalog.dart` and "
        "`canUseAction` on the definition -- and moving one without the other "
        "leaves the screen unreachable, which is how `user-firms` survived a "
        "fix aimed straight at it."
    )
