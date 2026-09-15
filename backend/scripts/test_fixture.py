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

It all happens in one firm, **TEST01**, in a schema of its own
(``test_fixtures``), so the four demo firms are never touched and a table
check in DbVisualizer against ``test_fixtures`` shows only test data. The
first run builds TEST01 -- create, provision, open the books, apply the GST
template, create the head office, assign the Wholesale profile -- using the
same endpoints plan section 27 tests. Later runs find it and move on.

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
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

#: The firm every fixture works in. Its code, schema and name are fixed so a
#: table check always knows where to look.
TEST_FIRM_CODE = "TEST01"
TEST_FIRM_SCHEMA = "test_fixtures"
TEST_FIRM_NAME = "Test Fixtures Firm"

#: Every account a fixture creates signs in with this. Twelve characters or
#: more, upper, lower, digit and symbol -- the policy -- and not a secret: it
#: guards throwaway accounts in a local test firm.
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
                payload = json.loads(response.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as error:
            raise FixtureError(_refusal(method, path, error)) from error
        except urllib.error.URLError as error:
            raise FixtureError(
                f"Cannot reach {self.base_url} ({error.reason}). Is the backend "
                "running?"
            ) from error
        return payload.get("data", payload)

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
# The test firm
# ---------------------------------------------------------------------------


def ensure_test_firm(admin: Api) -> str:
    """Find or build TEST01 until it can post, and return its id.

    Every step is one the API already makes idempotent, so a half-built firm --
    a provision that timed out, say -- is finished by running this again.
    """
    found = admin.call("GET", f"/api/v1/firms?search={TEST_FIRM_CODE}&page_size=10")
    firm = next((row for row in found if row.get("code") == TEST_FIRM_CODE), None)
    if firm is None:
        print(f"  creating {TEST_FIRM_CODE} (schema {TEST_FIRM_SCHEMA})")
        firm = admin.call(
            "POST",
            "/api/v1/firms",
            {
                "name": TEST_FIRM_NAME,
                "code": TEST_FIRM_CODE,
                "country": "IN",
                "currency_code": "INR",
                "financial_year_start": "2026-04-01",
                "deployment_mode": "SCHEMA",
                "schema_name": TEST_FIRM_SCHEMA,
                "notes": "Built by scripts/test_fixture.py. Test data only.",
            },
        )
    firm_id = str(firm["id"])
    if not firm.get("provisioned_at"):
        print("  provisioning storage (runs the migrations; a minute or two)")
        admin.call("POST", f"/api/v1/firms/{firm_id}/provision")
    readiness = admin.call("GET", f"/api/v1/firms/{firm_id}/readiness")
    steps = {step["key"]: step["status"] for step in readiness["steps"]}
    _finish_step(
        steps,
        "books",
        "opening the books",
        lambda: admin.call("POST", f"/api/v1/firms/{firm_id}/open-books", {}),
    )
    _finish_step(
        steps,
        "tax",
        "applying the GST template",
        lambda: admin.call("POST", f"/api/v1/firms/{firm_id}/apply-tax-template", {}),
    )
    _finish_step(
        steps,
        "branches",
        "creating the head office and main warehouse",
        lambda: admin.call("POST", f"/api/v1/firms/{firm_id}/create-default-branch"),
    )
    _ensure_profile(admin, firm_id)
    readiness = admin.call("GET", f"/api/v1/firms/{firm_id}/readiness")
    if not readiness["can_post"]:
        missing = [s["label"] for s in readiness["steps"] if s["status"] != "DONE"]
        raise FixtureError(f"{TEST_FIRM_CODE} still cannot post. Missing: {missing}")
    return firm_id


def _finish_step(
    steps: dict[str, str], key: str, doing: str, action: Callable[[], Any]
) -> None:
    """Run one setup action if readiness does not already call it done."""
    if steps.get(key) != "DONE":
        print(f"  {doing}")
        action()


def _ensure_profile(admin: Api, firm_id: str) -> None:
    """Give TEST01 the Wholesale profile, as WHOLE01 has.

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
        raise FixtureError(f"{TEST_FIRM_CODE}'s store offers no WHOLESALE profile.")
    print("  assigning the Wholesale business profile")
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
    firm_id: str
    lines: list[tuple[str, str]] = field(default_factory=list)
    admin_email: str | None = None
    admin_token: str | None = None
    role_id: str | None = None
    role_code: str | None = None

    def say(self, label: str, value: str) -> None:
        """Record one line of the handover block."""
        self.lines.append((label, value))


def _role_id(admin: Api, code: str) -> str:
    """Return the id of a seeded role by its code."""
    roles = admin.call("GET", f"/api/v1/roles?search={code}&page_size=50")
    match = next((row for row in roles if row["code"] == code), None)
    if match is None:
        raise FixtureError(f"No role with code {code}.")
    return str(match["id"])


def _new_user(admin: Api, built: Built, handle: str, full_name: str) -> str:
    """Create a user in TEST01 who can sign in straight away, and return the id."""
    email = f"{built.suffix}.{handle}@fixtures.local"
    user = admin.call(
        "POST",
        "/api/v1/users",
        {
            "email": email,
            "full_name": f"{full_name} ({built.suffix})",
            "password": FIXTURE_PASSWORD,
            "is_active": True,
            "force_password_change": False,
        },
    )
    user_id = str(user["id"])
    admin.call(
        "PUT",
        f"/api/v1/users/{user_id}/firms",
        {
            "assignments": [
                {"firm_id": built.firm_id, "is_primary": True, "is_active": True}
            ]
        },
    )
    return user_id


def build_firm_admin(admin: Api, built: Built) -> None:
    """Make a fresh firm administrator of TEST01, signed in and ready to act."""
    user_id = _new_user(admin, built, "admin", "Fixture Firm Admin")
    admin.call(
        "PUT",
        f"/api/v1/users/{user_id}/firms/{built.firm_id}/roles",
        {"ids": [_role_id(admin, "FIRM_ADMIN")]},
    )
    built.admin_email = f"{built.suffix}.admin@fixtures.local"
    built.admin_token = sign_in(admin, built.admin_email, FIXTURE_PASSWORD)
    built.say("Firm admin", f"{built.admin_email} / {FIXTURE_PASSWORD}")


def build_custom_role(admin: Api, built: Built) -> None:
    """Make a TEST01 custom role with the four Night Desk codes, as its admin."""
    build_firm_admin(admin, built)
    assert built.admin_token is not None
    firm_admin = admin.as_user(built.admin_token, built.firm_id)
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
    built.role_id, built.role_code = str(role["id"]), code
    built.say("Custom role", f"{code}  (Night Desk {built.suffix})")
    built.say("It carries", ", ".join(NIGHT_DESK_CODES))


def build_custom_template(admin: Api, built: Built) -> None:
    """Make a TEST01 job template bundling the custom role."""
    build_custom_role(admin, built)
    assert built.admin_token is not None and built.role_id is not None
    firm_admin = admin.as_user(built.admin_token, built.firm_id)
    code = f"{built.suffix}-night-desk-job"
    firm_admin.call(
        "POST",
        "/api/v1/user-templates",
        {
            "code": code,
            "name": f"Night Desk job {built.suffix}",
            "role_ids": [built.role_id],
        },
    )
    built.say("Job template", f"{code}  (Night Desk job {built.suffix})")


def build_role_holder(admin: Api, built: Built) -> None:
    """Make somebody in TEST01 who holds the custom role and nothing else."""
    build_custom_role(admin, built)
    assert built.role_id is not None
    user_id = _new_user(admin, built, "holder", "Night Desk Holder")
    admin.call(
        "PUT",
        f"/api/v1/users/{user_id}/firms/{built.firm_id}/roles",
        {"ids": [built.role_id]},
    )
    built.say(
        "Role holder", f"{built.suffix}.holder@fixtures.local / {FIXTURE_PASSWORD}"
    )


#: Every fixture, what it builds, and the cases that name it.
FIXTURES: dict[str, tuple[str, Callable[[Api, Built], None], str]] = {
    "firm-admin": (
        "A fresh firm administrator of TEST01.",
        build_firm_admin,
        "TC-ROLE-001, 002, 003, 004",
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
        "TC-ROLE-007, 008, 009",
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
            print(f"  {name:16} {what}\n  {'':16} used by {cases}\n")
        print("  baseline         Only make sure TEST01 exists and can post.")
        return 0
    if args.fixture not in FIXTURES and args.fixture != "baseline":
        print(f"Unknown fixture '{args.fixture}'. Run with 'list'.", file=sys.stderr)
        return 2

    api = Api(args.base_url)
    admin_email = os.environ.get("TEST_FIXTURE_ADMIN_EMAIL", "master.ops@agency.local")
    admin_password = os.environ.get("TEST_FIXTURE_ADMIN_PASSWORD", "DemoAdmin@12345")
    try:
        admin = api.as_user(sign_in(api, admin_email, admin_password), None)
        print(f"Checking {TEST_FIRM_CODE}...")
        firm_id = ensure_test_firm(admin)
        if args.fixture == "baseline":
            print(f"{TEST_FIRM_CODE} is ready. Firm id {firm_id}")
            return 0
        built = Built(suffix=_suffix(), firm_id=firm_id)
        print(f"Building '{args.fixture}' under suffix {built.suffix}...")
        FIXTURES[args.fixture][1](admin, built)
    except FixtureError as error:
        print(f"\nStopped: {error}", file=sys.stderr)
        return 1

    width = max(len(label) for label, _ in built.lines)
    print(f"\nFixture '{args.fixture}' ready")
    print(f"  {'Firm':{width}} : {TEST_FIRM_CODE}  (select it in the firm switcher)")
    for label, value in built.lines:
        print(f"  {label:{width}} : {value}")
    print(
        f"  {'Tables':{width}} : schema {TEST_FIRM_SCHEMA}; identity rows in platform"
    )
    print(f"  {'Suffix':{width}} : {built.suffix}  (everything this run made has it)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
