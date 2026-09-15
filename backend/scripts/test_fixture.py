"""Build the starting point for one manual test case, so any case runs alone.

The manual test plan used to be a chain: 20.1b needed the two-firm user 20.6
creates, 22.1 needed a cashier nobody had made, 25.10 deletes the role 25.2
creates so 25.9 can never be run twice, and 24.12 named an account whose
password had since changed. A tester who picked a row out of order met a
failure that belonged to the plan, not to the product.

This script is the other half of ``docs/INDEPENDENT_TEST_CASES.md``. Every case
there names the fixture it needs; running the fixture builds exactly that,
**through the real API** -- so the same rules a person meets on screen apply
to the setup -- and prints the logins and names to use. Nothing is reused
between runs: each run makes its own users and roles under a fresh suffix, so
a case that deletes a role or signs somebody out cannot break the next one.

It all happens in two firms of its own, **TEST01** and **TEST02**, each in a
schema of its own, so the four demo firms are never touched and a table check
against ``test_fixtures`` shows only test data. The first run builds them --
create, provision, open the books, apply the GST template, create the head
office, assign the Wholesale profile -- through the same endpoints plan
section 27 tests. Later runs find them and move on.

**One step is not an API call, on purpose.** Nothing in the API grants the
platform-administrator designation: a ``platform_admins`` row is deliberately
unreachable from anything a role can do, which is what closed the 2026-09-05
escalation. A fixture that needs a platform administrator therefore writes
that one row in-process, exactly as the seeder does, and says so. It writes no
audit row, which the seeder does not either.

The script signs in as a platform administrator to do the setup. It defaults
to ``master.ops@agency.local`` with the demo password, and **stops on the
first refused sign-in** rather than trying again: repeated guesses lock the
account. Override with ``TEST_FIXTURE_ADMIN_EMAIL`` and
``TEST_FIXTURE_ADMIN_PASSWORD``.

Needs the backend running. From ``backend``::

    ./.venv/Scripts/python.exe scripts/test_fixture.py list
    ./.venv/Scripts/python.exe scripts/test_fixture.py role-holder
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import string
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FixtureFirm:
    """One of the firms fixtures work in, and where its tables live."""

    code: str
    schema: str
    name: str
    mode: str = "SCHEMA"


#: The firms every fixture works in. Fixed codes and schemas, so a table check
#: always knows where to look. TEST02 exists for the cases that need somebody
#: in two firms, or two firms to keep apart.
TEST01 = FixtureFirm("TEST01", "test_fixtures", "Test Fixtures Firm")
TEST02 = FixtureFirm("TEST02", "test_fixtures_2", "Test Fixtures Second Firm")
FIXTURE_FIRMS = (TEST01, TEST02)

#: Two firms in the **shared** store, for the only cases that are about sharing
#: one: a unit of measure every firm in the store reads, and a custom-field
#: catalogue with no firm column. Built the first time `shared-pair` runs, and
#: never otherwise, because anything added to `firm_shared`'s catalogue is
#: visible to MEDI01 and FOOD01 as well.
TESTSH1 = FixtureFirm("TESTSH1", "firm_shared", "Test Shared Firm One", "SHARED")
TESTSH2 = FixtureFirm("TESTSH2", "firm_shared", "Test Shared Firm Two", "SHARED")

#: Every account a fixture creates signs in with this. Twelve characters or
#: more, upper, lower, digit and symbol -- the policy -- and not a secret: it
#: guards throwaway accounts in local test firms.
FIXTURE_PASSWORD = "Fixture@2026pw"

#: The four codes the "Night Desk" custom role carries. Both receipt codes on
#: purpose: `RECEIPT_CREATE` without `RECEIPT_VIEW` leaves the holder no
#: Receipts screen to record on, which plan row 25.3 once got wrong.
NIGHT_DESK_CODES = ("SALES_VIEW", "CUSTOMER_VIEW", "RECEIPT_VIEW", "RECEIPT_CREATE")

Json = dict[str, Any]


class FixtureError(RuntimeError):
    """Raise when a setup step is refused, carrying the API's message."""


@dataclass
class Api:
    """Talk JSON to the running backend."""

    base_url: str
    token: str | None = None
    firm_id: str | None = None

    def call(
        self, method: str, path: str, body: Json | None = None
    ) -> Any:  # noqa: ANN401 -- the API answers objects and lists alike
        """Send one request and return ``data``, or raise with the API's words."""
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.firm_id:
            headers["X-Firm-ID"] = self.firm_id
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=None if body is None else json.dumps(body).encode("utf-8"),
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            raise FixtureError(_refusal(method, path, error)) from error
        except urllib.error.URLError as error:
            raise FixtureError(
                f"Cannot reach {self.base_url} ({error.reason}). Is the backend "
                "running?"
            ) from error
        payload = json.loads(raw) if raw else {}
        return payload.get("data", payload) if isinstance(payload, dict) else payload

    def as_user(self, token: str, firm_id: str | None) -> Api:
        """Return a client acting as somebody else, optionally inside a firm."""
        return Api(self.base_url, token=token, firm_id=firm_id)


def _refusal(method: str, path: str, error: urllib.error.HTTPError) -> str:
    """Say what the API refused and why, in its own words."""
    try:
        detail = json.loads(error.read().decode("utf-8"))
        message = (detail.get("error") or {}).get("message") or detail
        details = (detail.get("error") or {}).get("details")
    except (ValueError, AttributeError):
        message, details = error.reason, None
    suffix = f" {details}" if details else ""
    return f"{method} {path} answered {error.code}: {message}{suffix}"


def sign_in(api: Api, email: str, password: str) -> str:
    """Return an access token, refusing to retry a failed sign-in."""
    try:
        data = api.call(
            "POST", "/api/v1/auth/login", {"email": email, "password": password}
        )
    except FixtureError as error:
        raise FixtureError(
            f"Sign-in as {email} was refused, and this script does not try again "
            f"because repeated failures lock the account. {error}"
        ) from error
    if data.get("must_change_password"):
        raise FixtureError(
            f"{email} must change its password before it can be used. Sign in "
            "once on the desktop, or set TEST_FIXTURE_ADMIN_EMAIL to another "
            "platform administrator."
        )
    return str(data["access_token"])


def _suffix() -> str:
    """Return a short name no earlier run has used: ``t0916`` plus four."""
    alphabet = string.ascii_lowercase + string.digits
    return date.today().strftime("t%m%d") + "".join(
        secrets.choice(alphabet) for _ in range(4)
    )


# ---------------------------------------------------------------------------
# The test firms
# ---------------------------------------------------------------------------


def create_firm(admin: Api, firm: FixtureFirm) -> Json:
    """Find a fixture firm by code, or create its record, and return the row.

    Creation only records the intent -- nothing is provisioned, opened or
    assigned -- which is exactly the state plan section 27 starts from.
    """
    found = admin.call("GET", f"/api/v1/firms?search={firm.code}&page_size=10")
    row = next((item for item in found if item.get("code") == firm.code), None)
    if row is not None:
        return dict(row)
    print(f"  creating {firm.code} ({firm.mode}, {firm.schema})")
    body: Json = {
        "name": firm.name,
        "code": firm.code,
        "country": "IN",
        "currency_code": "INR",
        "financial_year_start": "2026-04-01",
        "deployment_mode": firm.mode,
        "notes": "Built by scripts/test_fixture.py. Test data only.",
    }
    if firm.mode == "SCHEMA":
        body["schema_name"] = firm.schema
    return dict(admin.call("POST", "/api/v1/firms", body))


def provision_firm(admin: Api, firm: FixtureFirm, row: Json) -> str:
    """Build a dedicated firm's tables if they are not there, and return its id."""
    firm_id = str(row["id"])
    if firm.mode != "SHARED" and not row.get("provisioned_at"):
        print(f"  provisioning {firm.code} (runs the migrations; a minute or two)")
        admin.call("POST", f"/api/v1/firms/{firm_id}/provision")
    return firm_id


def ensure_firm(admin: Api, firm: FixtureFirm) -> str:
    """Find or build one fixture firm until it can post, and return its id.

    Every step is one the API already makes idempotent, so a half-built firm --
    a provision that timed out, say -- is finished by running this again.
    """
    firm_id = provision_firm(admin, firm, create_firm(admin, firm))
    readiness = admin.call("GET", f"/api/v1/firms/{firm_id}/readiness")
    steps = {step["key"]: step["status"] for step in readiness["steps"]}
    base = f"/api/v1/firms/{firm_id}"
    for key, doing, method, path, body in (
        ("books", "opening the books", "POST", f"{base}/open-books", {}),
        ("tax", "applying the GST template", "POST", f"{base}/apply-tax-template", {}),
        (
            "branches",
            "creating the head office",
            "POST",
            f"{base}/create-default-branch",
            None,
        ),
    ):
        if steps.get(key) != "DONE":
            print(f"  {firm.code}: {doing}")
            admin.call(method, path, body)
    _ensure_profile(admin, firm, firm_id)
    readiness = admin.call("GET", f"/api/v1/firms/{firm_id}/readiness")
    if not readiness["can_post"]:
        missing = [s["label"] for s in readiness["steps"] if s["status"] != "DONE"]
        raise FixtureError(f"{firm.code} still cannot post. Missing: {missing}")
    return firm_id


def _ensure_profile(admin: Api, firm: FixtureFirm, firm_id: str) -> None:
    """Give a fixture firm the Wholesale profile, as WHOLE01 has.

    Without one the firm trades as GENERIC, whose module set is not the one
    the demo firms show -- and the desktop's sidebar filters on it, so a case
    that says "Finance is in the sidebar" would be testing the profile rather
    than the permission.
    """
    current = admin.call(
        "GET", f"/api/v1/business-framework/firms/{firm_id}/profile-assignment"
    )
    rows = current if isinstance(current, list) else [current]
    if any(row and row.get("business_profile_id") for row in rows):
        return
    profiles = admin.call("GET", f"/api/v1/business-framework/firms/{firm_id}/profiles")
    wholesale = next((p for p in profiles if p.get("code") == "WHOLESALE"), None)
    if wholesale is None:
        raise FixtureError(f"{firm.code}'s store offers no WHOLESALE profile.")
    print(f"  {firm.code}: assigning the Wholesale business profile")
    admin.call(
        "PUT",
        f"/api/v1/business-framework/firms/{firm_id}/profile-assignment",
        {"business_profile_id": wholesale["id"], "is_active": True},
    )


# ---------------------------------------------------------------------------
# Building blocks a fixture composes
# ---------------------------------------------------------------------------


@dataclass
class Built:
    """Hold what a fixture made, for printing and for the next block."""

    suffix: str
    admin: Api
    firms: dict[str, str]
    lines: list[tuple[str, str]] = field(default_factory=list)
    ids: dict[str, str] = field(default_factory=dict)
    tokens: dict[str, str] = field(default_factory=dict)
    firms_used: list[str] = field(default_factory=lambda: [TEST01.code])
    known: dict[str, FixtureFirm] = field(
        default_factory=lambda: {firm.code: firm for firm in FIXTURE_FIRMS}
    )

    def say(self, label: str, value: str) -> None:
        """Record one line of the handover block."""
        self.lines.append((label, value))

    def email(self, handle: str) -> str:
        """Return the address of this run's user with the given handle."""
        return f"{self.suffix}.{handle}@fixtures.local"

    def add_firm(self, firm: FixtureFirm, firm_id: str) -> None:
        """Make a firm this run built available to the blocks below."""
        self.firms[firm.code] = firm_id
        self.known[firm.code] = firm

    def run_firm(self, letter: str, name: str) -> FixtureFirm:
        """Describe a firm of this run's own: code, schema and name all carry it."""
        return FixtureFirm(
            f"{self.suffix.upper()}-{letter}",
            f"fx_{self.suffix}_{letter.lower()}",
            f"{name} {self.suffix}",
        )

    def as_(self, handle: str, firm: FixtureFirm | None = TEST01) -> Api:
        """Return a client signed in as this run's user, inside a firm."""
        if handle not in self.tokens:
            self.tokens[handle] = sign_in(
                self.admin, self.email(handle), FIXTURE_PASSWORD
            )
        return self.admin.as_user(
            self.tokens[handle], self.firms[firm.code] if firm else None
        )


def role_id(built: Built, code: str) -> str:
    """Return the id of a seeded role by its code."""
    roles = built.admin.call("GET", f"/api/v1/roles?search={code}&page_size=50")
    match = next((row for row in roles if row["code"] == code), None)
    if match is None:
        raise FixtureError(f"No role with code {code}.")
    return str(match["id"])


def new_user(
    built: Built,
    handle: str,
    full_name: str,
    firms: Sequence[FixtureFirm] = (TEST01,),
) -> str:
    """Create a user who can sign in straight away, in these firms, first primary.

    An empty ``firms`` makes somebody in no firm at all -- which the plan's
    20.2b needs, and which a platform administrator with no memberships is.
    """
    user = built.admin.call(
        "POST",
        "/api/v1/users",
        {
            "email": built.email(handle),
            "full_name": f"{full_name} ({built.suffix})",
            "password": FIXTURE_PASSWORD,
            "is_active": True,
            "force_password_change": False,
        },
    )
    user_id = str(user["id"])
    if firms:
        built.admin.call(
            "PUT",
            f"/api/v1/users/{user_id}/firms",
            {
                "assignments": [
                    {
                        "firm_id": built.firms[firm.code],
                        "is_primary": index == 0,
                        "is_active": True,
                    }
                    for index, firm in enumerate(firms)
                ]
            },
        )
    built.ids[handle] = user_id
    return user_id


def firm_roles(
    built: Built, user_id: str, firm: FixtureFirm, codes: Sequence[str]
) -> None:
    """Give somebody these seeded roles in one firm."""
    built.admin.call(
        "PUT",
        f"/api/v1/users/{user_id}/firms/{built.firms[firm.code]}/roles",
        {"ids": [role_id(built, code) for code in codes]},
    )


def global_roles(built: Built, user_id: str, codes: Sequence[str]) -> None:
    """Give somebody these seeded roles in every firm they belong to."""
    built.admin.call(
        "PUT",
        f"/api/v1/users/{user_id}/roles",
        {"ids": [role_id(built, code) for code in codes]},
    )


def designate_platform_admin(built: Built, user_id: str, scope: str) -> None:
    """Make somebody a platform administrator -- the one in-process step.

    No route grants the designation, deliberately; see the module docstring.
    Imported lazily so the fixtures that do not need it stay a plain HTTP
    client with no database connection.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from uuid import UUID  # noqa: PLC0415

    import app.core.database.all_models  # noqa: F401, PLC0415
    from app.core.config.settings import Settings  # noqa: PLC0415
    from app.core.database.engine import DatabaseManager, EngineFactory  # noqa: PLC0415
    from app.identity.models import PlatformAdmin  # noqa: PLC0415

    actor = UUID(str(built.admin.call("GET", "/api/v1/me")["id"]))
    manager = DatabaseManager(EngineFactory.database_config_from_settings(Settings()))
    with manager.sessions(schema="platform").session() as session:
        session.add(
            PlatformAdmin(
                user_id=UUID(user_id), scope=scope, created_by=actor, updated_by=actor
            )
        )
        session.commit()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def build_firm_admin(built: Built) -> None:
    """Make a fresh firm administrator of TEST01, signed in and ready to act."""
    user_id = new_user(built, "admin", "Fixture Firm Admin")
    firm_roles(built, user_id, TEST01, ["FIRM_ADMIN"])
    built.say("Firm admin", f"{built.email('admin')} / {FIXTURE_PASSWORD}")


def build_custom_role(built: Built) -> None:
    """Make a TEST01 custom role with the four Night Desk codes, as its admin."""
    build_firm_admin(built)
    firm_admin = built.as_("admin")
    code = f"{built.suffix}-night-desk"
    role = firm_admin.call(
        "POST", "/api/v1/roles", {"code": code, "name": f"Night Desk {built.suffix}"}
    )
    permission_ids = []
    for wanted in NIGHT_DESK_CODES:
        found = firm_admin.call(
            "GET", f"/api/v1/permissions?search={wanted}&page_size=50"
        )
        match = next((row for row in found if row["code"] == wanted), None)
        if match is None:
            raise FixtureError(f"Permission {wanted} is not offered to a firm admin.")
        permission_ids.append(match["id"])
    firm_admin.call(
        "PUT", f"/api/v1/roles/{role['id']}/permissions", {"ids": permission_ids}
    )
    built.ids["custom_role"] = str(role["id"])
    built.say("Custom role", f"{code}  (Night Desk {built.suffix})")
    built.say("It carries", ", ".join(NIGHT_DESK_CODES))


def build_custom_template(built: Built) -> None:
    """Make a TEST01 job template bundling the custom role."""
    build_custom_role(built)
    code = f"{built.suffix}-night-desk-job"
    built.as_("admin").call(
        "POST",
        "/api/v1/user-templates",
        {
            "code": code,
            "name": f"Night Desk job {built.suffix}",
            "role_ids": [built.ids["custom_role"]],
        },
    )
    built.say("Job template", f"{code}  (Night Desk job {built.suffix})")


def build_role_holder(built: Built) -> None:
    """Make somebody in TEST01 who holds the custom role and nothing else."""
    build_custom_role(built)
    user_id = new_user(built, "holder", "Night Desk Holder")
    built.admin.call(
        "PUT",
        f"/api/v1/users/{user_id}/firms/{built.firms[TEST01.code]}/roles",
        {"ids": [built.ids["custom_role"]]},
    )
    built.say("Role holder", f"{built.email('holder')} / {FIXTURE_PASSWORD}")


def build_platform_admin(built: Built) -> None:
    """Make an ALL_FIRMS platform administrator who belongs to no firm at all.

    The shape that made plan section 26 visible: a token carrying every code,
    and no membership to pick a firm from.
    """
    user_id = new_user(built, "platform", "Fixture Platform Admin", firms=())
    designate_platform_admin(built, user_id, "ALL_FIRMS")
    built.firms_used = [TEST01.code, TEST02.code]
    built.say("Platform admin", f"{built.email('platform')} / {FIXTURE_PASSWORD}")
    built.say("Scope", "ALL_FIRMS, and a member of no firm")


def build_platform_admin_member(built: Built) -> None:
    """Make an ALL_FIRMS platform administrator who is a member of both test firms."""
    user_id = new_user(
        built, "platformm", "Fixture Platform Member", firms=(TEST01, TEST02)
    )
    designate_platform_admin(built, user_id, "ALL_FIRMS")
    built.firms_used = [TEST01.code, TEST02.code]
    built.say("Platform admin", f"{built.email('platformm')} / {FIXTURE_PASSWORD}")
    built.say("Scope", "ALL_FIRMS, and a member of TEST01 (primary) and TEST02")


def build_two_firm_user(built: Built) -> None:
    """Make an ordinary user in both test firms, with roles in each tier.

    `SALES_EXECUTIVE` in TEST01 and `CUSTOMER_SUPPORT` in every firm, so My
    profile has both an "In every firm" and an "In TEST01" group to show, and
    neither role carries `USER_VIEW` -- the point of reading one's own profile.
    """
    user_id = new_user(built, "twofirm", "Two Firm User", firms=(TEST01, TEST02))
    firm_roles(built, user_id, TEST01, ["SALES_EXECUTIVE"])
    global_roles(built, user_id, ["CUSTOMER_SUPPORT"])
    built.firms_used = [TEST01.code, TEST02.code]
    built.say("Two-firm user", f"{built.email('twofirm')} / {FIXTURE_PASSWORD}")
    built.say("Memberships", "TEST01 (primary), TEST02")
    built.say("Roles", "SALES_EXECUTIVE in TEST01; CUSTOMER_SUPPORT in every firm")


def build_unprovisioned_firm(built: Built) -> None:
    """Make a platform admin and a SCHEMA firm of this run's own, not provisioned."""
    build_platform_admin(built)
    firm = built.run_firm("U", "Unprovisioned")
    built.add_firm(firm, str(create_firm(built.admin, firm)["id"]))
    built.firms_used = [firm.code]
    built.say("New firm", f"{firm.code}  ({firm.name}), SCHEMA, not provisioned")


def build_unfinished_firm(built: Built) -> None:
    """Make a platform admin and a provisioned SCHEMA firm with nothing else.

    No profile, no books, no tax, no branch, nobody in it: every row of the
    setup panel still to do, so the first press of each button is the one the
    case is about.
    """
    build_platform_admin(built)
    firm = built.run_firm("F", "Unfinished")
    row = create_firm(built.admin, firm)
    built.add_firm(firm, provision_firm(built.admin, firm, row))
    built.firms_used = [firm.code]
    built.say("New firm", f"{firm.code}  ({firm.name}), SCHEMA, provisioned only")


def build_ready_firm(built: Built) -> None:
    """Make a finished firm of this run's own, with a firm admin and a receipt.

    Its own store, so the custom-field cases can make a field mandatory, or
    change the firm's profile, without breaking anybody else's case. The
    receipt posts to Accounts receivable and Cash, which is what locks those
    two control accounts -- the half of the Control Accounts screen a fresh
    firm cannot show.
    """
    build_platform_admin(built)
    firm = built.run_firm("R", "Ready")
    firm_id = ensure_firm(built.admin, firm)
    built.add_firm(firm, firm_id)
    built.firms_used = [firm.code]
    user_id = new_user(built, "readyadmin", "Ready Firm Admin", firms=(firm,))
    firm_roles(built, user_id, firm, ["FIRM_ADMIN"])
    viewer_id = new_user(built, "readyviewer", "Ready Firm Viewer", firms=(firm,))
    firm_roles(built, viewer_id, firm, ["VIEWER"])
    inside = built.admin.as_user(built.admin.token or "", firm_id)
    # A fresh store holds no product category, and a Mandatory Attributes rule
    # is written against one -- two, so "this category only" can be seen.
    for code, name in (("FXAMB", "Fixture Ambient"), ("FXCHL", "Fixture Chilled")):
        inside.call("POST", "/api/v1/products/categories", {"code": code, "name": name})
    customer = inside.call(
        "POST",
        "/api/v1/customers",
        {
            "code": "FXCUST",
            "name": f"Fixture Customer {built.suffix}",
            "customer_type": "BUSINESS",
            "currency_code": "INR",
        },
    )
    receipt = inside.call(
        "POST",
        "/api/v1/receipts",
        {
            "party_id": customer["id"],
            "settlement_date": date.today().isoformat(),
            "amount": "500.00",
            "method": "CASH",
            "narration": "Posted by scripts/test_fixture.py to lock two accounts.",
        },
    )
    built.say("New firm", f"{firm.code}  ({firm.name}), SCHEMA, finished, WHOLESALE")
    built.say("Firm admin", f"{built.email('readyadmin')} / {FIXTURE_PASSWORD}")
    built.say("Viewer", f"{built.email('readyviewer')} / {FIXTURE_PASSWORD}  (VIEWER)")
    built.say("Categories", "FXAMB (Fixture Ambient), FXCHL (Fixture Chilled)")
    built.say("Customer", f"FXCUST  (Fixture Customer {built.suffix})")
    built.say(
        "Receipt",
        f"{receipt.get('settlement_number', '?')}, 500.00 cash -- "
        "Accounts receivable and Cash now hold posted lines",
    )


def build_shared_pair(built: Built) -> None:
    """Make a platform admin, and a firm admin in each shared-store test firm.

    The platform administrator is for Dynamic Attributes, which only a
    platform administrator may write to. Both firms get the Wholesale profile,
    as TEST01 has, so the screens a case names are the ones on offer.
    """
    build_platform_admin(built)
    for firm, handle in ((TESTSH1, "shadmin1"), (TESTSH2, "shadmin2")):
        firm_id = str(create_firm(built.admin, firm)["id"])
        _ensure_profile(built.admin, firm, firm_id)
        built.add_firm(firm, firm_id)
        user_id = new_user(built, handle, f"{firm.code} Admin", firms=(firm,))
        firm_roles(built, user_id, firm, ["FIRM_ADMIN"])
        built.say(f"{firm.code} admin", f"{built.email(handle)} / {FIXTURE_PASSWORD}")
    built.firms_used = [TESTSH1.code, TESTSH2.code]
    built.say("Shared store", "both firms live in firm_shared, beside MEDI01, FOOD01")


def build_platform_operator(built: Built) -> None:
    """Make a PLATFORM-scope administrator: runs the platform, refused the books.

    A member of TEST01 (primary) and TEST02 with no role in either -- the
    shape plan section 16 met on `superadmin`, whose memberships still show in
    the switcher while its designation grants nothing inside a firm.
    """
    user_id = new_user(built, "operator", "Platform Operator", firms=(TEST01, TEST02))
    designate_platform_admin(built, user_id, "PLATFORM")
    built.firms_used = [TEST01.code, TEST02.code]
    built.say("Operator", f"{built.email('operator')} / {FIXTURE_PASSWORD}")
    built.say("Scope", "PLATFORM; member of TEST01 (primary) and TEST02, no roles")


def build_sales_executive(built: Built) -> None:
    """Make somebody in TEST01 holding SALES_EXECUTIVE alone, as whole01.sales1."""
    user_id = new_user(built, "seller", "Fixture Seller")
    firm_roles(built, user_id, TEST01, ["SALES_EXECUTIVE"])
    built.say("Seller", f"{built.email('seller')} / {FIXTURE_PASSWORD}")
    built.say("Roles", "SALES_EXECUTIVE in TEST01, nothing else")


def build_manual_hire(built: Built) -> None:
    """Make a firm admin, and a TEST01 user whose two roles were picked by hand."""
    build_firm_admin(built)
    user_id = new_user(built, "manual", "Manual Hire")
    firm_roles(built, user_id, TEST01, ["SALES_EXECUTIVE", "CUSTOMER_SUPPORT"])
    built.say("Manual hire", f"{built.email('manual')} / {FIXTURE_PASSWORD}")
    built.say("Roles", "SALES_EXECUTIVE and CUSTOMER_SUPPORT in TEST01")


def build_two_tier_hire(built: Built) -> None:
    """Make a user with roles in both tiers, and an administrator of each tier.

    Global `VIEWER` and `CUSTOMER_SUPPORT`; `ACCOUNTANT` and
    `INVENTORY_MANAGER` in TEST01. A template overwrites the tier its caller
    writes and never the other, and this is the person that shows it.
    """
    build_firm_admin(built)
    build_platform_admin(built)
    user_id = new_user(built, "twotier", "Two Tier Hire")
    global_roles(built, user_id, ["VIEWER", "CUSTOMER_SUPPORT"])
    firm_roles(built, user_id, TEST01, ["ACCOUNTANT", "INVENTORY_MANAGER"])
    built.firms_used = [TEST01.code]
    built.say("Two-tier hire", f"{built.email('twotier')} / {FIXTURE_PASSWORD}")
    built.say("Every firm", "VIEWER, CUSTOMER_SUPPORT")
    built.say("In TEST01", "ACCOUNTANT, INVENTORY_MANAGER")


def build_firm_template_hire(built: Built) -> None:
    """Make a TEST01 job template and somebody hired into it."""
    build_firm_admin(built)
    firm_admin = built.as_("admin")
    code = f"{built.suffix}-night-counter"
    template = firm_admin.call(
        "POST",
        "/api/v1/user-templates",
        {
            "code": code,
            "name": f"Night Counter {built.suffix}",
            "role_ids": [
                role_id(built, "CASHIER"),
                role_id(built, "BILLING_EXECUTIVE"),
            ],
        },
    )
    user_id = new_user(built, "nighthire", "Night Counter Hire")
    firm_admin.call(
        "POST",
        f"/api/v1/users/{user_id}/apply-template",
        {"template_id": template["id"]},
    )
    built.say("Job template", f"{code}  (Night Counter {built.suffix})")
    built.say("Hired into it", f"{built.email('nighthire')} / {FIXTURE_PASSWORD}")


def build_clone_source(built: Built) -> None:
    """Make a firm admin, and a TEST01 seller to hire somebody like."""
    build_firm_admin(built)
    user_id = new_user(built, "source", "Source Seller")
    firm_roles(built, user_id, TEST01, ["SALES_EXECUTIVE"])
    built.say("Source", f"{built.email('source')} / {FIXTURE_PASSWORD}")
    built.say("Source roles", "SALES_EXECUTIVE in TEST01 only")


#: Every fixture, what it builds, and the cases that name it.
FIXTURES: dict[str, tuple[str, Callable[[Built], None], str]] = {
    "firm-admin": (
        "A fresh firm administrator of TEST01.",
        build_firm_admin,
        "TC-ROLE-001..004, TC-PLAT-005, TC-ME-007, TC-FIRM-016, "
        "TC-TMPL-001..004, TC-TMPL-011",
    ),
    "custom-role": (
        "firm-admin + a custom role with the four Night Desk codes.",
        build_custom_role,
        "TC-ROLE-005",
    ),
    "custom-template": (
        "custom-role + a job template bundling it.",
        build_custom_template,
        "TC-ROLE-006",
    ),
    "role-holder": (
        "custom-role + a user holding that role and nothing else.",
        build_role_holder,
        "TC-ROLE-007..009",
    ),
    "platform-admin": (
        "An ALL_FIRMS platform administrator who belongs to no firm.",
        build_platform_admin,
        "TC-PLAT-001..003, TC-ME-006, TC-FIRM-001..003",
    ),
    "platform-admin-member": (
        "An ALL_FIRMS platform administrator who belongs to both test firms.",
        build_platform_admin_member,
        "TC-PLAT-004",
    ),
    "two-firm-user": (
        "An ordinary user in TEST01 and TEST02, with roles in both tiers.",
        build_two_firm_user,
        "TC-ME-001..005, TC-ME-008",
    ),
    "unprovisioned-firm": (
        "platform-admin + a SCHEMA firm of this run's own, not provisioned.",
        build_unprovisioned_firm,
        "TC-FIRM-004..006",
    ),
    "unfinished-firm": (
        "platform-admin + a provisioned SCHEMA firm with nothing else done.",
        build_unfinished_firm,
        "TC-FIRM-007..013",
    ),
    "ready-firm": (
        "A finished firm of this run's own, its admin, and a posted receipt.",
        build_ready_firm,
        "TC-FIRM-014, TC-FIRM-015, TC-FIELD-001..012",
    ),
    "shared-pair": (
        "A firm admin in each of TESTSH1 and TESTSH2, in the shared store.",
        build_shared_pair,
        "TC-FIELD-013, TC-FIELD-014",
    ),
    "platform-operator": (
        "A PLATFORM-scope administrator in TEST01 and TEST02, with no roles.",
        build_platform_operator,
        "TC-TIER-001..003",
    ),
    "sales-executive": (
        "A TEST01 user holding SALES_EXECUTIVE alone.",
        build_sales_executive,
        "TC-TMPL-009",
    ),
    "manual-hire": (
        "firm-admin + a TEST01 user with two roles picked by hand.",
        build_manual_hire,
        "TC-TMPL-005",
    ),
    "two-tier-hire": (
        "firm-admin + platform-admin + a user with roles in both tiers.",
        build_two_tier_hire,
        "TC-TMPL-006..008",
    ),
    "firm-template-hire": (
        "firm-admin + a TEST01 job template + somebody hired into it.",
        build_firm_template_hire,
        "TC-TMPL-010",
    ),
    "clone-source": (
        "firm-admin + a TEST01 seller to hire somebody like.",
        build_clone_source,
        "TC-HIRE-001..004",
    ),
}


def main() -> int:
    """Build the named fixture and print the handover block."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("fixture", help="a fixture name, 'baseline', or 'list'")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("TEST_FIXTURE_BASE_URL", "http://localhost:8000"),
    )
    args = parser.parse_args()

    if args.fixture == "list":
        print("Fixtures (each run builds fresh, under its own suffix):\n")
        for name, (what, _, cases) in FIXTURES.items():
            print(f"  {name:22} {what}\n  {'':22} used by {cases}\n")
        print(f"  {'baseline':22} Only make sure TEST01 and TEST02 exist and can post.")
        return 0
    if args.fixture not in FIXTURES and args.fixture != "baseline":
        print(f"Unknown fixture '{args.fixture}'. Run with 'list'.", file=sys.stderr)
        return 2

    api = Api(args.base_url)
    admin_email = os.environ.get("TEST_FIXTURE_ADMIN_EMAIL", "master.ops@agency.local")
    admin_password = os.environ.get("TEST_FIXTURE_ADMIN_PASSWORD", "DemoAdmin@12345")
    try:
        admin = api.as_user(sign_in(api, admin_email, admin_password), None)
        print("Checking the test firms...")
        firms = {firm.code: ensure_firm(admin, firm) for firm in FIXTURE_FIRMS}
        if args.fixture == "baseline":
            for firm in FIXTURE_FIRMS:
                print(
                    f"  {firm.code} ready: id {firms[firm.code]}, schema {firm.schema}"
                )
            return 0
        built = Built(suffix=_suffix(), admin=admin, firms=firms)
        print(f"Building '{args.fixture}' under suffix {built.suffix}...")
        FIXTURES[args.fixture][1](built)
    except FixtureError as error:
        print(f"\nStopped: {error}", file=sys.stderr)
        return 1

    schemas = {code: firm.schema for code, firm in built.known.items()}
    width = max(len(label) for label, _ in [*built.lines, ("Tables", "")])
    print(f"\nFixture '{args.fixture}' ready")
    for label, value in built.lines:
        print(f"  {label:{width}} : {value}")
    tables = "; ".join(f"{code} in schema {schemas[code]}" for code in built.firms_used)
    print(f"  {'Tables':{width}} : {tables}; identity rows in platform")
    print(f"  {'Suffix':{width}} : {built.suffix}  (everything this run made has it)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
