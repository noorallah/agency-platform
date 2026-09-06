"""A firm administrator can reach every module its firm operates.

`_operational_permissions` in `app/identity/system_seed.py` is a hand-kept list
of permission groups, and `FIRM_ADMIN` and `FIRM_MANAGER` are built from it. A
group added to `PERMISSION_GROUPS` is not added to that list, and five slipped
through: `credit_note`, `proforma`, `einvoice`, `loyalty` and `tcs` each shipped
with a module, a screen and a seeded gate, and none reached the role whose
description is running the firm and every module.

`SALES_MANAGER` names most of those codes individually, so the screens were
reachable by somebody, which is why it went unnoticed until the access-control
survey on 2026-09-06 asked the question mechanically.

The point of this file is the first test, not the second. Pinning the five that
were missed catches nothing; asking **which groups are operational** and
failing when the list omits one catches the sixth.
"""

# ruff: noqa: D103

from app.identity.system_seed import (
    PERMISSION_GROUPS,
    PLATFORM_PERMISSION_CODES,
    ROLE_PERMISSION_CODES,
)

#: Groups that are neither a firm's business nor something the platform holds
#: back, and are deliberately not part of `_operational_permissions`.
#:
#: `user`, `role` and `permission` are `_firm_administration`: `FIRM_ADMIN`
#: holds them and `FIRM_MANAGER` deliberately does not, which is the whole
#: distinction between the two roles. Listing them here rather than adding them
#: to the operational set is what keeps that distinction.
_FIRM_ADMINISTRATION = frozenset({"user", "role", "permission"})


def _operational_groups() -> frozenset[str]:
    """Return the groups that are a firm's own business.

    Derived rather than listed: a group is operational when it is neither
    withheld from firms entirely (`PLATFORM_PERMISSION_CODES` -- platform,
    firm, system administration and the high-risk verbs over posted books) nor
    part of administering the firm's own people.
    """
    return frozenset(
        group
        for group, codes in PERMISSION_GROUPS.items()
        if group not in _FIRM_ADMINISTRATION
        and not set(codes) & PLATFORM_PERMISSION_CODES
    )


def test_a_firm_admin_holds_every_operational_code() -> None:
    """The guard that finds the next group to drift.

    When this fails, a permission group has been added to `PERMISSION_GROUPS`
    without being added to `_operational_permissions`. The firm's own
    administrator cannot open whatever it gates, and nothing else will say so:
    the screen is simply absent, which looks like a product decision.
    """
    granted = ROLE_PERMISSION_CODES["FIRM_ADMIN"]
    missing = {
        group: sorted(set(PERMISSION_GROUPS[group]) - granted)
        for group in _operational_groups()
        if set(PERMISSION_GROUPS[group]) - granted
    }

    assert not missing, (
        "`FIRM_ADMIN` cannot reach these operational permission groups:\n  "
        + "\n  ".join(
            f"{group}: {', '.join(codes)}" for group, codes in missing.items()
        )
        + "\n\nAdd the group to `_operational_permissions` in "
        "`app/identity/system_seed.py`, **and** write a migration granting the "
        "codes to `FIRM_ADMIN` and `FIRM_MANAGER` -- `seed_system_rbac` is "
        "called only by `generate_sample_data.py` and never at startup, so a "
        "database that already exists gets nothing from the seed alone. "
        "`20260906_0130` is the pattern."
    )


def test_a_firm_manager_holds_the_same_less_the_administration() -> None:
    """The one difference between the two roles, and it should stay the one.

    `FIRM_MANAGER` is `_operational_permissions` minus the codes for
    administering people. If it ever differs from `FIRM_ADMIN` by anything
    else, the two roles have quietly stopped meaning what they say.
    """
    admin = ROLE_PERMISSION_CODES["FIRM_ADMIN"]
    manager = ROLE_PERMISSION_CODES["FIRM_MANAGER"]
    administration = {
        code for group in _FIRM_ADMINISTRATION for code in PERMISSION_GROUPS[group]
    }

    assert manager <= admin
    assert not manager & administration
    # Settings are the administrator's, and `LICENSE_MANAGE` is nobody's here.
    assert admin - manager == administration | {
        "SETTINGS_VIEW",
        "SETTINGS_UPDATE",
        "AUDIT_LOG_VIEW",
    }


def test_the_five_that_were_missed_are_granted() -> None:
    """A named regression, for anybody reading `git log` later.

    The general guard above is what catches the sixth; this one records which
    five were missed, so a bisect lands on a test that says what happened
    rather than on a set-difference message.
    """
    granted = ROLE_PERMISSION_CODES["FIRM_ADMIN"]

    assert {
        "CREDIT_NOTE_VIEW",
        "CREDIT_NOTE_MANAGE",
        "CREDIT_NOTE_APPROVE",
        "PROFORMA_VIEW",
        "PROFORMA_MANAGE",
        "EINVOICE_VIEW",
        "EINVOICE_MANAGE",
        "LOYALTY_VIEW",
        "LOYALTY_MANAGE",
        "LOYALTY_MANAGE_SETTINGS",
        "TCS_VIEW",
        "TCS_MANAGE",
    } <= granted


def test_the_platform_codes_stay_out_of_it() -> None:
    """Widening the operational set must not widen it into the platform.

    `FIRM_VIEW` is the one to watch: it reads like a firm code and is a
    platform one, and it is what the desktop's New-user gate demanded until
    2026-09-06.
    """
    granted = ROLE_PERMISSION_CODES["FIRM_ADMIN"]

    # Two, and both deliberate. `PLATFORM_PERMISSION_CODES` answers "what may
    # a firm administrator not *grant*", which is a different question from
    # "what may they hold" -- the seed hands them `SETTINGS_VIEW` and
    # `SETTINGS_UPDATE` directly, so they can configure their own firm without
    # being able to pass the codes on.
    assert granted & PLATFORM_PERMISSION_CODES == {
        "SETTINGS_VIEW",
        "SETTINGS_UPDATE",
        # Their own firm's trail, not the platform's: `audit_scope` reads one
        # trail chosen by firm context and still applies the membership check.
        "AUDIT_LOG_VIEW",
    }
    # And not the crash log, which is telemetry for whoever maintains the
    # product rather than anything a firm owns.
    assert "DIAGNOSTICS_VIEW" not in granted
    assert "FIRM_VIEW" not in granted
    assert "VOID_INVOICE" not in granted
    assert "EDIT_POSTED_TRANSACTION" not in granted
