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
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FixtureFirm:
    """One of the firms fixtures work in, and where its tables live."""

    code: str
    schema: str
    name: str
    mode: str = "SCHEMA"
    profile: str = "WHOLESALE"


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
    """Give a fixture firm its business profile -- Wholesale, as WHOLE01 has.

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
    wanted = next((p for p in profiles if p.get("code") == firm.profile), None)
    if wanted is None:
        raise FixtureError(f"{firm.code}'s store offers no {firm.profile} profile.")
    print(f"  {firm.code}: assigning the {firm.profile} business profile")
    admin.call(
        "PUT",
        f"/api/v1/business-framework/firms/{firm_id}/profile-assignment",
        {"business_profile_id": wanted["id"], "is_active": True},
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

    def run_firm(
        self, letter: str, name: str, profile: str = "WHOLESALE"
    ) -> FixtureFirm:
        """Describe a firm of this run's own: code, schema and name all carry it."""
        return FixtureFirm(
            f"{self.suffix.upper()}-{letter}",
            f"fx_{self.suffix}_{letter.lower()}",
            f"{name} {self.suffix}",
            profile=profile,
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


def sales_chain(built: Built, firm: FixtureFirm = TEST01) -> dict[str, str]:
    """Sell this run's own product to this run's own customer, end to end.

    Product (GST 18 local, PIECE), 50 opening stock at 60, a sales order for
    10 at 100, approved; a delivery note for all 10, approved and dispatched;
    an invoice for 5 off that note, **approved** -- it posts -- and a second
    for the other 5, **cancelled** while a draft. Everything through the same
    routes the desktop calls, so each step meets the rules a person would.
    Returns the ids, keyed by what they are.
    """
    admin = built.admin.as_user(built.admin.token or "", built.firms[firm.code])
    tag = built.suffix.upper()
    warehouse = by_code(admin, "/api/v1/warehouses", "MAIN")
    branch = by_code(admin, "/api/v1/branches", "HO")
    product = stocked_product(built, admin, warehouse, branch)
    customer = admin.call(
        "POST",
        "/api/v1/customers",
        {
            "code": f"{tag}-C",
            "name": f"Fixture Buyer {built.suffix}",
            "customer_type": "BUSINESS",
            "currency_code": "INR",
        },
    )
    return _sell(built, admin, warehouse, branch, product, customer)


def stocked_product(built: Built, admin: Api, warehouse: Json, branch: Json) -> Json:
    """Make this run's own product -- GST 18 local, PIECE -- with 50 on hand at 60."""
    today = date.today().isoformat()
    tag = built.suffix.upper()
    units = admin.call("GET", "/api/v1/uom-framework/uoms?page_size=100")
    piece = next(u["id"] for u in units if u["code"] == "PIECE")
    product = admin.call(
        "POST",
        "/api/v1/products",
        {
            "code": f"{tag}-P",
            "name": f"Fixture Product {built.suffix}",
            "product_type": "STOCK_ITEM",
            "tax_profile_group_code": "GST_18_LOCAL",
            "selling_price": "100",
            "purchase_price": "60",
            "base_uom_id": piece,
            "inventory_uom_id": piece,
            "sales_uom_id": piece,
            "purchase_uom_id": piece,
        },
    )
    opening = admin.call(
        "POST",
        "/api/v1/inventory/opening-stock",
        {
            "warehouse_id": warehouse["id"],
            "branch_id": branch["id"],
            "reference_number": f"{tag}-OS",
            "posting_date": today,
            "lines": [
                {"product_id": product["id"], "quantity": "50", "unit_cost": "60"}
            ],
        },
    )
    admin.call("POST", f"/api/v1/inventory/opening-stock/{opening['id']}/post")
    return dict(product)


def _sell(
    built: Built,
    admin: Api,
    warehouse: Json,
    branch: Json,
    product: Json,
    customer: Json,
) -> dict[str, str]:
    """Order, deliver and invoice 10 of a product to a customer; see sales_chain."""
    today = date.today().isoformat()
    tag = built.suffix.upper()
    order = admin.call(
        "POST",
        "/api/v1/sales-orders",
        {
            "customer_id": customer["id"],
            "order_date": today,
            "warehouse_id": warehouse["id"],
            "branch_id": branch["id"],
            "lines": [
                {
                    "line_number": 1,
                    "product_id": product["id"],
                    "quantity": "10",
                    "unit_price": "100",
                }
            ],
        },
    )
    admin.call("POST", f"/api/v1/sales-orders/{order['id']}/approve")
    order_line = admin.call("GET", f"/api/v1/sales-orders/{order['id']}")["lines"][0]
    note = admin.call(
        "POST",
        "/api/v1/delivery-notes",
        {
            "sales_order_id": order["id"],
            "delivery_date": today,
            "lines": [
                {
                    "sales_order_line_id": order_line["id"],
                    "line_number": 1,
                    "current_delivery_quantity": "10",
                }
            ],
        },
    )
    admin.call("POST", f"/api/v1/delivery-notes/{note['id']}/approve")
    admin.call("POST", f"/api/v1/delivery-notes/{note['id']}/dispatch")
    note_line = admin.call("GET", f"/api/v1/delivery-notes/{note['id']}")["lines"][0]

    def invoice(quantity: str) -> Json:
        return dict(
            admin.call(
                "POST",
                "/api/v1/sales-invoices",
                {
                    "customer_id": customer["id"],
                    "branch_id": branch["id"],
                    "invoice_date": today,
                    "source_documents": [
                        {
                            "source_document_type": "DELIVERY_NOTE",
                            "source_document_id": note["id"],
                        }
                    ],
                    "lines": [
                        {
                            "source_document_type": "DELIVERY_NOTE",
                            "source_document_id": note["id"],
                            "source_document_line_id": note_line["id"],
                            "line_number": 1,
                            "current_invoice_quantity": quantity,
                        }
                    ],
                },
            )
        )

    approved = invoice("5")
    approved = admin.call("POST", f"/api/v1/sales-invoices/{approved['id']}/approve")
    cancelled = invoice("5")
    admin.call(
        "POST",
        f"/api/v1/sales-invoices/{cancelled['id']}/cancel",
        {"reason": "Cancelled by scripts/test_fixture.py"},
    )
    built.say("Product", f"{tag}-P  (Fixture Product {built.suffix}), 50 in MAIN")
    built.say("Customer", f"{tag}-C  (Fixture Buyer {built.suffix})")
    built.say("Sales order", f"{order.get('order_number')} for 10, approved")
    built.say("Delivery note", f"{note.get('delivery_note_number')} for 10, dispatched")
    built.say("Invoice", f"{approved.get('invoice_number')} for 5, APPROVED")
    built.say("Cancelled", f"{cancelled.get('invoice_number')} for 5, CANCELLED")
    return {
        "product": str(product["id"]),
        "customer": str(customer["id"]),
        "order": str(order["id"]),
        "note": str(note["id"]),
        "invoice": str(approved["id"]),
        "cancelled_invoice": str(cancelled["id"]),
    }


def by_code(admin: Api, path: str, code: str) -> Json:
    """Return the row with this code from a list, never the list's first row.

    List order is not a promise: a warehouse another run added can come back
    first, and a fixture that took ``[0]`` put its stock there instead of in
    MAIN. The default branch and warehouse the setup panel makes are HO and
    MAIN in every fixture firm.
    """
    rows = admin.call("GET", f"{path}?search={code}&page_size=100")
    match = next((row for row in rows if row.get("code") == code), None)
    if match is None:
        raise FixtureError(f"No row with code {code} at {path}.")
    return dict(match)


def run_places(built: Built, admin: Api) -> tuple[Json, Json, Json, Json]:
    """Make a state, district and city of this run's own under India.

    A fixture firm's store holds India -- the GST template adds it -- and
    nothing beneath it, so a place picker has no second rung until somebody
    makes one. Writing geography needs a platform administrator.
    """
    tag = built.suffix.upper()
    geo = "/api/v1/sales-territories/geo"
    india = next(c for c in admin.call("GET", f"{geo}/countries") if c["code"] == "IN")
    state = admin.call(
        "POST",
        f"{geo}/states",
        {
            "country_id": india["id"],
            "code": f"{tag}ST",
            "name": f"State {built.suffix}",
        },
    )
    district = admin.call(
        "POST",
        f"{geo}/districts",
        {
            "state_id": state["id"],
            "code": f"{tag}DT",
            "name": f"District {built.suffix}",
        },
    )
    city = admin.call(
        "POST",
        f"{geo}/cities",
        {
            "district_id": district["id"],
            "code": f"{tag}CT",
            "name": f"City {built.suffix}",
        },
    )
    return dict(india), dict(state), dict(district), dict(city)


def purchase_chain(built: Built, stage: str) -> dict[str, str]:
    """Buy this run's own product from this run's own vendor, up to a stage.

    ``buy-ready`` makes the vendor and a product with nothing on hand;
    ``approved`` adds a purchase order for 10 at 100, submitted and approved;
    ``received`` completes two goods receipts against it, 4 then 6;
    ``invoiced`` approves a supplier invoice for the 6. The product starts at
    zero, so every stock figure in the cases is absolute. Through the routes
    the desktop calls, except the invoice, which no screen raises yet.
    """
    stages = ("buy-ready", "approved", "received", "invoiced")
    admin = built.admin.as_user(built.admin.token or "", built.firms[TEST01.code])
    today = date.today().isoformat()
    tag = built.suffix.upper()
    ids: dict[str, str] = {}
    warehouse = by_code(admin, "/api/v1/warehouses", "MAIN")
    branch = by_code(admin, "/api/v1/branches", "HO")
    units = admin.call("GET", "/api/v1/uom-framework/uoms?page_size=100")
    piece = next(u["id"] for u in units if u["code"] == "PIECE")
    vendor = admin.call(
        "POST",
        "/api/v1/vendors",
        {"code": f"{tag}-V", "name": f"Fixture Supplier {built.suffix}"},
    )
    product = admin.call(
        "POST",
        "/api/v1/products",
        {
            "code": f"{tag}-B",
            "name": f"Bought Item {built.suffix}",
            "product_type": "STOCK_ITEM",
            "tax_profile_group_code": "GST_18_LOCAL",
            "purchase_price": "100",
            "selling_price": "150",
            "base_uom_id": piece,
            "inventory_uom_id": piece,
            "sales_uom_id": piece,
            "purchase_uom_id": piece,
        },
    )
    ids.update(vendor=str(vendor["id"]), product=str(product["id"]))
    built.say("Vendor", f"{tag}-V  (Fixture Supplier {built.suffix})")
    built.say("Product", f"{tag}-B  (Bought Item {built.suffix}), 0 on hand")
    built.say("Warehouse", f"{warehouse['code']} under branch {branch['code']}")
    if stages.index(stage) < 1:
        return ids
    order = admin.call(
        "POST",
        "/api/v1/purchases",
        {
            "branch_id": branch["id"],
            "warehouse_id": warehouse["id"],
            "vendor_id": vendor["id"],
            "purchase_date": today,
            "lines": [
                {
                    "product_id": product["id"],
                    "ordered_quantity": "10",
                    "unit_price": "100",
                    "purchase_uom_id": piece,
                    "inventory_uom_id": piece,
                }
            ],
        },
    )
    admin.call("POST", f"/api/v1/purchases/{order['id']}/submit")
    order = admin.call("POST", f"/api/v1/purchases/{order['id']}/approve")
    order_line = admin.call("GET", f"/api/v1/purchases/{order['id']}")["lines"][0]
    ids["order"] = str(order["id"])
    built.say("Purchase order", f"{order.get('po_number')} for 10 at 100, APPROVED")
    if stages.index(stage) < 2:
        return ids
    receipts = []
    for quantity in ("4", "6"):
        receipt = admin.call(
            "POST",
            "/api/v1/goods-receipts",
            {
                "purchase_order_id": order["id"],
                "receipt_date": today,
                "lines": [
                    {
                        "purchase_order_line_id": order_line["id"],
                        "line_number": 1,
                        "current_receipt_quantity": quantity,
                        "warehouse_id": warehouse["id"],
                    }
                ],
            },
        )
        receipt = admin.call("POST", f"/api/v1/goods-receipts/{receipt['id']}/complete")
        receipts.append(receipt)
        built.say(f"Receipt of {quantity}", f"{receipt.get('grn_number')}, COMPLETED")
    ids.update(receipt_4=str(receipts[0]["id"]), receipt_6=str(receipts[1]["id"]))
    if stages.index(stage) < 3:
        return ids
    receipt_line = admin.call("GET", f"/api/v1/goods-receipts/{receipts[1]['id']}")[
        "lines"
    ][0]
    invoice = admin.call(
        "POST",
        "/api/v1/purchase-invoices",
        {
            "vendor_id": vendor["id"],
            "branch_id": branch["id"],
            "invoice_date": today,
            "supplier_invoice_number": f"{tag}-SUP-1",
            "supplier_invoice_date": today,
            "source_documents": [
                {
                    "source_document_type": "GOODS_RECEIPT",
                    "source_document_id": receipts[1]["id"],
                }
            ],
            "lines": [
                {
                    "source_document_type": "GOODS_RECEIPT",
                    "source_document_id": receipts[1]["id"],
                    "source_document_line_id": receipt_line["id"],
                    "line_number": 1,
                    "current_invoice_quantity": "6",
                    "unit_price": "100",
                }
            ],
        },
    )
    invoice = admin.call("POST", f"/api/v1/purchase-invoices/{invoice['id']}/approve")
    ids["invoice"] = str(invoice["id"])
    built.say(
        "Supplier invoice",
        f"{invoice.get('invoice_number')} ({tag}-SUP-1) for the 6, APPROVED",
    )
    return ids


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


def build_template_offering(built: Built) -> None:
    """Make a platform admin to write templates, and a TEST01 admin to read them."""
    build_firm_admin(built)
    build_platform_admin(built)


def build_shared_member(built: Built) -> None:
    """Make people who cross firms, and an administrator on each side of them.

    A firm admin of TEST01 and a platform admin; **Shared Member** in TEST02
    (primary) and TEST01 with no roles, whose profile TEST01's admin may not
    edit; and **TEST02 Only**, in TEST02 alone, whom TEST01's admin administers
    nothing about.
    """
    build_firm_admin(built)
    build_platform_admin(built)
    new_user(built, "shared", "Shared Member", firms=(TEST02, TEST01))
    new_user(built, "t2only", "TEST02 Only", firms=(TEST02,))
    built.firms_used = [TEST01.code, TEST02.code]
    built.say("Shared member", f"{built.email('shared')}  (TEST02 primary, TEST01)")
    built.say("TEST02 only", f"{built.email('t2only')}  (TEST02 alone)")


def build_shared_member_roles(built: Built) -> None:
    """Make shared-member, with Shared Member holding a role in every tier.

    `VIEWER` in every firm, `SALES_MANAGER` in TEST01, `CASHIER` in TEST02 --
    three separate rows, so a save that collapses the tiers shows at once.
    """
    build_shared_member(built)
    user_id = built.ids["shared"]
    global_roles(built, user_id, ["VIEWER"])
    firm_roles(built, user_id, TEST01, ["SALES_MANAGER"])
    firm_roles(built, user_id, TEST02, ["CASHIER"])
    built.say(
        "Its roles", "VIEWER everywhere; SALES_MANAGER in TEST01; CASHIER in TEST02"
    )


def build_invoiced(built: Built) -> None:
    """Make a TEST01 firm admin and a sale of this run's own, invoiced."""
    build_firm_admin(built)
    built.ids.update(sales_chain(built))


def build_loyalty_viewer(built: Built) -> None:
    """Make somebody in TEST01 who may read the loyalty scheme and not change it."""
    user_id = new_user(built, "loyaltyview", "Loyalty Viewer")
    firm_roles(built, user_id, TEST01, ["SALES_MANAGER"])
    built.say("Loyalty viewer", f"{built.email('loyaltyview')} / {FIXTURE_PASSWORD}")
    built.say("Roles", "SALES_MANAGER in TEST01 (LOYALTY_VIEW, not the settings code)")


def build_cashier(built: Built) -> None:
    """Make a TEST01 cashier holding CASHIER alone, and a customer to take from.

    CASHIER alone is the point: the seeded Counter Sales template pairs it with
    BILLING_EXECUTIVE, which is what hid a cashier's empty sidebar.
    """
    user_id = new_user(built, "cashier", "Fixture Cashier")
    firm_roles(built, user_id, TEST01, ["CASHIER"])
    admin = built.admin.as_user(built.admin.token or "", built.firms[TEST01.code])
    tag = built.suffix.upper()
    admin.call(
        "POST",
        "/api/v1/customers",
        {
            "code": f"{tag}-TILL",
            "name": f"Till Customer {built.suffix}",
            "customer_type": "BUSINESS",
            "currency_code": "INR",
        },
    )
    built.say("Cashier", f"{built.email('cashier')} / {FIXTURE_PASSWORD}")
    built.say("Roles", "CASHIER in TEST01, nothing else")
    built.say("Customer", f"{tag}-TILL  (Till Customer {built.suffix})")


def build_accountant(built: Built) -> None:
    """Make a TEST01 user holding ACCOUNTANT alone; none is seeded anywhere."""
    user_id = new_user(built, "accountant", "Fixture Accountant")
    firm_roles(built, user_id, TEST01, ["ACCOUNTANT"])
    built.say("Accountant", f"{built.email('accountant')} / {FIXTURE_PASSWORD}")
    built.say("Roles", "ACCOUNTANT in TEST01, nothing else")


def build_outsider(built: Built) -> None:
    """Make somebody TEST01 does not employ, and an administrator of each tier.

    **Outsider** works in TEST02 alone, as a cashier there -- somebody
    TEST01's admin can look up and bring in, but must not learn anything
    about beyond a name and an address.
    """
    build_firm_admin(built)
    build_platform_admin(built)
    user_id = new_user(built, "outsider", "Outsider", firms=(TEST02,))
    firm_roles(built, user_id, TEST02, ["CASHIER"])
    built.firms_used = [TEST01.code, TEST02.code]
    built.say("Outsider", f"{built.email('outsider')}  (TEST02 only, CASHIER there)")


def build_outsider_added(built: Built) -> None:
    """Make outsider, already added to TEST01 by its admin as Counter Sales.

    The same two calls Add existing user makes: the membership write, which
    merges for a firm admin, and the template.
    """
    build_outsider(built)
    firm_admin = built.as_("admin")
    user_id = built.ids["outsider"]
    firm_admin.call(
        "PUT",
        f"/api/v1/users/{user_id}/firms",
        {
            "assignments": [
                {
                    "firm_id": built.firms[TEST01.code],
                    "is_primary": False,
                    "is_active": True,
                }
            ]
        },
    )
    templates = firm_admin.call("GET", "/api/v1/user-templates?page_size=100")
    counter = next(row for row in templates if row["code"] == "counter-sales")
    firm_admin.call(
        "POST",
        f"/api/v1/users/{user_id}/apply-template",
        {"template_id": counter["id"]},
    )
    built.say("Added", "to TEST01 by its admin, as Counter Sales")


def build_lock_target(built: Built) -> None:
    """Make an ordinary TEST01 user to lock out, switch off, delete and restore.

    Beside a firm admin and a platform admin, because the cases on this person
    turn on which of the two may act: a firm admin clears a lock, only a
    platform admin sees the deleted, restores them, or sets a password.
    """
    build_firm_admin(built)
    build_platform_admin(built)
    user_id = new_user(built, "target", "Lock Target")
    firm_roles(built, user_id, TEST01, ["SALES_EXECUTIVE"])
    built.firms_used = [TEST01.code]
    built.say("Target", f"{built.email('target')} / {FIXTURE_PASSWORD}")
    built.say("Roles", "SALES_EXECUTIVE in TEST01")


def build_isolation_pair(built: Built, shared: bool = False) -> None:
    """Make a customer of this run's own in each of TEST01 and TEST02.

    Named so a search for the other firm's one is a real isolation check: the
    same suffix, different letters, and the name of neither firm's customer
    can appear in the other.
    """
    build_platform_admin(built)
    tag = built.suffix.upper()
    pairs = [(TEST01, "ONE"), (TEST02, "TWO")]
    if shared:
        for firm in (TESTSH1, TESTSH2):
            built.add_firm(firm, str(create_firm(built.admin, firm)["id"]))
        pairs = [(TESTSH1, "SHONE"), (TESTSH2, "SHTWO")]
    for firm, letter in pairs:
        inside = built.admin.as_user(built.admin.token or "", built.firms[firm.code])
        inside.call(
            "POST",
            "/api/v1/customers",
            {
                "code": f"{tag}-{letter}",
                "name": f"Isolation {letter.title()} {built.suffix}",
                "customer_type": "BUSINESS",
                "currency_code": "INR",
            },
        )
        built.say(
            f"In {firm.code}",
            f"{tag}-{letter}  (Isolation {letter.title()} {built.suffix})",
        )
    built.firms_used = [firm.code for firm, _ in pairs]


def build_shared_isolation_pair(built: Built) -> None:
    """Make the same pair in TESTSH1 and TESTSH2, which share one schema."""
    build_isolation_pair(built, shared=True)


def build_customer_master(built: Built) -> None:
    """Make a fully described TEST01 customer, the places and segments it names.

    Addresses, a contact, a credit limit, payment terms, a 7.5% standing
    discount and a segment -- every field an edit that dumps its whole write
    model would reset -- plus a state, district, city and PIN of this run's
    own for the place picker (TEST01's store holds India and nothing under
    it), two segments, and a stocked product to sell against a credit limit.
    """
    build_firm_admin(built)
    build_sales_executive(built)
    tag = built.suffix.upper()
    admin = built.admin.as_user(built.admin.token or "", built.firms[TEST01.code])
    india, state, district, city = run_places(built, admin)
    groups = {}
    for key, name, rate in (("RET", "Retailer", "1.75"), ("WHL", "Wholesaler", "3.25")):
        groups[key] = admin.call(
            "POST",
            "/api/v1/customers/groups",
            {
                "code": f"{tag}-{key}",
                "name": f"{name} {built.suffix}",
                "default_discount_percent": rate,
            },
        )
    customer = admin.call(
        "POST",
        "/api/v1/customers",
        {
            "code": f"{tag}-CM",
            "name": f"Master Check {built.suffix}",
            "customer_type": "BUSINESS",
            "currency_code": "INR",
            "phone": "+919800000100",
            "credit_limit": "50000",
            "payment_terms_days": 30,
            "default_discount_percent": "7.5",
            "customer_group_id": groups["RET"]["id"],
            "addresses": [
                {
                    "address_type": "BILLING",
                    "address_line1": "12 Fixture Street",
                    "city": f"City {built.suffix}",
                    "state": f"State {built.suffix}",
                    "country": "IN",
                    "postal_code": "600001",
                    "country_id": india["id"],
                    "state_id": state["id"],
                    "district_id": district["id"],
                    "city_id": city["id"],
                    "is_default_billing": True,
                }
            ],
            "contacts": [
                {
                    "name": "Fixture Contact",
                    "mobile": "+919800000101",
                    "is_primary": True,
                }
            ],
        },
    )
    warehouse = by_code(admin, "/api/v1/warehouses", "MAIN")
    branch = by_code(admin, "/api/v1/branches", "HO")
    stocked_product(built, admin, warehouse, branch)
    built.ids["customer"] = str(customer["id"])
    built.say("Customer", f"{tag}-CM  (Master Check {built.suffix})")
    built.say(
        "It carries",
        "a billing address, a contact, limit 50,000, 30 days, 7.5% standing, "
        f"segment {tag}-RET",
    )
    built.say("Segments", f"{tag}-RET Retailer 1.75%, {tag}-WHL Wholesaler 3.25%")
    built.say(
        "Places", f"India > State {built.suffix} > District > City {built.suffix}"
    )
    built.say("Product", f"{tag}-P  (Fixture Product {built.suffix}), 50 in stock")


def build_invoiced_part_paid(built: Built) -> None:
    """Make invoiced, with 200 of the 590 invoice collected against it."""
    build_invoiced(built)
    admin = built.admin.as_user(built.admin.token or "", built.firms[TEST01.code])
    receipt = admin.call(
        "POST",
        "/api/v1/receipts",
        {
            "party_id": built.ids["customer"],
            "settlement_date": date.today().isoformat(),
            "amount": "200.00",
            "method": "BANK",
            "allocations": [{"invoice_id": built.ids["invoice"], "amount": "200.00"}],
        },
    )
    built.say(
        "Receipt", f"{receipt.get('settlement_number')} for 200 against the invoice"
    )


def build_vendor_master(built: Built) -> None:
    """Make a TEST01 vendor carrying one of each child collection.

    A contact, an address, a bank account, a tax record, an attachment and a
    note -- the six collections an update used to empty when it did not name
    them -- and a category and a type of this run's own, not yet on it.
    """
    build_firm_admin(built)
    tag = built.suffix.upper()
    admin = built.admin.as_user(built.admin.token or "", built.firms[TEST01.code])
    category = admin.call(
        "POST",
        "/api/v1/vendors/categories",
        {"code": f"{tag}-CAT", "name": f"Category {built.suffix}"},
    )
    kind = admin.call(
        "POST",
        "/api/v1/vendors/types",
        {"code": f"{tag}-TYP", "name": f"Type {built.suffix}"},
    )
    admin.call(
        "POST",
        "/api/v1/vendors",
        {
            "code": f"{tag}-V",
            "name": f"Supply Check {built.suffix}",
            "phone": "+919800000200",
            "contacts": [
                {
                    "name": "Vendor Contact",
                    "mobile": "+919800000201",
                    "is_primary": True,
                }
            ],
            "addresses": [
                {
                    "address_type": "OFFICE",
                    "address_line1": "7 Supplier Lane",
                    "is_primary": True,
                }
            ],
            "banking": [
                {
                    "bank_name": "Fixture Bank",
                    "account_name": f"Supply Check {built.suffix}",
                    "account_number": "000111222333",
                    "ifsc": "FXBK0000001",
                    "is_primary": True,
                }
            ],
            "tax": [{"pan": "ABCDE1234F", "is_primary": True}],
            "attachments": [
                {
                    "file_name": "agreement.pdf",
                    "file_url": "https://example.invalid/agreement.pdf",
                }
            ],
            "notes": [{"note": f"Created by the fixture {built.suffix}."}],
        },
    )
    built.ids["vendor_category"] = str(category["id"])
    built.ids["vendor_type"] = str(kind["id"])
    built.say("Vendor", f"{tag}-V  (Supply Check {built.suffix})")
    built.say(
        "It carries",
        "1 contact, 1 address, 1 bank account, 1 tax record, 1 attachment, 1 note",
    )
    built.say(
        "Category", f"{tag}-CAT  (Category {built.suffix}), not on the vendor yet"
    )
    built.say("Type", f"{tag}-TYP  (Type {built.suffix}), not on the vendor yet")


def build_product_master(built: Built) -> None:
    """Make a TEST01 product with every slot filled and a Case to scan."""
    build_firm_admin(built)
    tag = built.suffix.upper()
    admin = built.admin.as_user(built.admin.token or "", built.firms[TEST01.code])
    category = admin.call(
        "POST",
        "/api/v1/products/categories",
        {"code": f"{tag}-PC", "name": f"Shelf {built.suffix}"},
    )
    units = {
        u["code"]: u["id"]
        for u in admin.call("GET", "/api/v1/uom-framework/uoms?page_size=100")
    }
    product = admin.call(
        "POST",
        "/api/v1/products",
        {
            "code": f"{tag}-PM",
            "name": f"Slot Check {built.suffix}",
            "product_type": "STOCK_ITEM",
            "category_id": category["id"],
            "tax_profile_group_code": "GST_18_LOCAL",
            "selling_price": "100",
            "base_uom_id": units["PIECE"],
            "inventory_uom_id": units["PIECE"],
            "sales_uom_id": units["PIECE"],
            "purchase_uom_id": units["BOX"],
        },
    )
    barcode = "89" + str(
        int(date.today().strftime("%m%d")) * 100000 + secrets.randbelow(100000)
    )
    admin.call(
        "POST",
        f"/api/v1/uom-framework/products/{product['id']}/packaging-levels",
        {
            "level_name": "Case",
            "conversion_to_base_factor": "12",
            "uom_id": units["CASE"],
            "barcode": barcode,
        },
    )
    built.say("Product", f"{tag}-PM  (Slot Check {built.suffix})")
    built.say(
        "It carries", f"category {tag}-PC, GST_18_LOCAL, PIECE x3 and BOX to buy in"
    )
    built.say("Case", f"barcode {barcode}, 12 pieces")


def build_branch_master(built: Built) -> None:
    """Make a TEST02 default branch and warehouse with every field set.

    TEST02, because a branch made default demotes the firm's previous one,
    and the selling fixtures work in TEST01. Street lines, a city, a GST
    registration and the default flag on the branch; a capacity and every
    capability flag on the warehouse -- what a rename used to clear. Also
    writes two import files, one with a clash on its last row.
    """
    build_platform_admin(built)
    user_id = new_user(built, "t2admin", "TEST02 Firm Admin", firms=(TEST02,))
    firm_roles(built, user_id, TEST02, ["FIRM_ADMIN"])
    tag = built.suffix.upper()
    admin = built.admin.as_user(built.admin.token or "", built.firms[TEST02.code])
    india, state, district, city = run_places(built, admin)
    branch = admin.call(
        "POST",
        "/api/v1/branches",
        {
            "code": f"{tag}-BR",
            "name": f"Keep Branch {built.suffix}",
            "address_line1": "1 Keep Street",
            "address_line2": "Keep Nagar",
            "country_id": india["id"],
            "state_id": state["id"],
            "district_id": district["id"],
            "city_id": city["id"],
            "gst_registration": True,
            "pan": "ABCDE1234F",
            "is_default": True,
        },
    )
    flags = {
        "temperature_controlled": True,
        "cold_storage": True,
        "hazardous_storage": False,
        "has_receiving_area": True,
        "has_dispatch_area": True,
        "has_returns_area": False,
        "has_inspection_area": True,
        "has_packing_area": False,
        "has_loading_dock": True,
    }
    admin.call(
        "POST",
        "/api/v1/warehouses",
        {
            "branch_id": branch["id"],
            "code": f"{tag}-WH",
            "name": f"Keep Warehouse {built.suffix}",
            "capacity": "1000",
            "capacity_unit": "SQFT",
            "is_default": True,
            **flags,
        },
    )
    folder = Path(tempfile.gettempdir()).resolve() / "agency-fixtures"
    folder.mkdir(exist_ok=True)
    header = "code,name,address_line1,currency_code,status"
    rows = [
        f"{tag}-I{n},Import {n} {built.suffix},{n} Import Road,INR,ACTIVE"
        for n in range(1, 5)
    ]
    bad = folder / f"{built.suffix}-branches-clash.csv"
    good = folder / f"{built.suffix}-branches-clean.csv"
    bad.write_text(
        "\n".join([header, *rows, f"{tag}-BR,Clash {built.suffix},x,INR,ACTIVE"]) + "\n"
    )
    good.write_text("\n".join([header, *rows]) + "\n")
    built.firms_used = [TEST02.code]
    built.say("TEST02 admin", f"{built.email('t2admin')} / {FIXTURE_PASSWORD}")
    built.say(
        "Branch", f"{tag}-BR  (Keep Branch {built.suffix}), default, GST registered"
    )
    built.say(
        "Warehouse",
        f"{tag}-WH  (Keep Warehouse {built.suffix}), 1000 SQFT, six flags on",
    )
    built.say("Import, clash", str(bad))
    built.say("Import, clean", str(good))


def build_config_firm(built: Built) -> None:
    """Make ready-firm, plus a vendor and a product bought in packs of one kg.

    A store of the run's own, because the cases here change what a whole
    store holds: a firm-wide conversion rule reaches every product in it, and
    a business profile's features reach every firm on the profile.
    `<SUFFIX>-DET` carries its own PACK to KG rule at a factor of 1.
    """
    build_ready_firm(built)
    firm = built.known[f"{built.suffix.upper()}-R"]
    tag = built.suffix.upper()
    admin = built.admin.as_user(built.admin.token or "", built.firms[firm.code])
    units = {
        u["code"]: u["id"]
        for u in admin.call("GET", "/api/v1/uom-framework/uoms?page_size=100")
    }
    admin.call(
        "POST",
        "/api/v1/vendors",
        {"code": f"{tag}-V", "name": f"Pack Supplier {built.suffix}"},
    )
    product = admin.call(
        "POST",
        "/api/v1/products",
        {
            "code": f"{tag}-DET",
            "name": f"Detergent 1kg {built.suffix}",
            "product_type": "STOCK_ITEM",
            "tax_profile_group_code": "GST_18_LOCAL",
            "purchase_price": "100",
            "base_uom_id": units["KG"],
            "inventory_uom_id": units["KG"],
            "sales_uom_id": units["PACK"],
            "purchase_uom_id": units["PACK"],
        },
    )
    admin.call(
        "POST",
        "/api/v1/uom-framework/conversion-rules",
        {
            "product_id": product["id"],
            "from_uom_id": units["PACK"],
            "to_uom_id": units["KG"],
            "conversion_factor": "1",
            "effective_from": "2020-01-01",
        },
    )
    built.say("Vendor", f"{tag}-V  (Pack Supplier {built.suffix})")
    built.say(
        "Product",
        f"{tag}-DET  (Detergent 1kg {built.suffix}): buy in PACK, stock in KG",
    )
    built.say("Its own rule", "PACK -> KG, factor 1")


def _buyer(built: Built, stage: str) -> None:
    """Make a TEST01 firm admin and a purchase of this run's own, to a stage."""
    build_firm_admin(built)
    built.ids.update(purchase_chain(built, stage))


def build_buy_ready(built: Built) -> None:
    """Make a firm admin, a vendor and a product with nothing on hand."""
    _buyer(built, "buy-ready")


def build_po_approved(built: Built) -> None:
    """Make buy-ready plus an approved purchase order for 10."""
    _buyer(built, "approved")


def build_po_received(built: Built) -> None:
    """Make po-approved with all 10 received: receipts of 4 and 6, completed."""
    _buyer(built, "received")


def build_po_invoiced(built: Built) -> None:
    """Make po-received with the receipt of 6 billed on an approved invoice."""
    _buyer(built, "invoiced")


def build_stock_ready(built: Built) -> None:
    """Make a TEST01 firm admin, 50 of a product in MAIN, and a second warehouse."""
    build_firm_admin(built)
    tag = built.suffix.upper()
    admin = built.admin.as_user(built.admin.token or "", built.firms[TEST01.code])
    warehouse = by_code(admin, "/api/v1/warehouses", "MAIN")
    branch = by_code(admin, "/api/v1/branches", "HO")
    stocked_product(built, admin, warehouse, branch)
    admin.call(
        "POST",
        "/api/v1/warehouses",
        {
            "branch_id": branch["id"],
            "code": f"{tag}-W2",
            "name": f"Overflow {built.suffix}",
        },
    )
    built.say("Product", f"{tag}-P  (Fixture Product {built.suffix}), 50 in MAIN")
    built.say(
        "Second warehouse", f"{tag}-W2  (Overflow {built.suffix}), under HO, empty"
    )


def _own_trading_firm(built: Built, letter: str, name: str, profile: str) -> Api:
    """Finish a firm of this run's own on a profile, with a firm admin in it."""
    build_platform_admin(built)
    firm = built.run_firm(letter, name, profile)
    firm_id = ensure_firm(built.admin, firm)
    built.add_firm(firm, firm_id)
    built.firms_used = [firm.code]
    user_id = new_user(built, "tradeadmin", f"{name} Admin", firms=(firm,))
    firm_roles(built, user_id, firm, ["FIRM_ADMIN"])
    built.say("New firm", f"{firm.code}  ({firm.name}), SCHEMA, finished, {profile}")
    built.say("Firm admin", f"{built.email('tradeadmin')} / {FIXTURE_PASSWORD}")
    return built.admin.as_user(built.admin.token or "", firm_id)


def build_pharma_firm(built: Built) -> None:
    """Make a Pharmacy firm of this run's own with batches to dispatch.

    `<SUFFIX>-AMX` holds three batches of 10: one already expired, one
    expiring in 20 days, one in 400. An approved order takes 5 of it, and a
    second product with 3 on hand has an approved order for 10.
    """
    admin = _own_trading_firm(built, "P", "Pharmacy", "PHARMACY")
    tag = built.suffix.upper()
    today = date.today()
    warehouse = by_code(admin, "/api/v1/warehouses", "MAIN")
    branch = by_code(admin, "/api/v1/branches", "HO")
    units = admin.call("GET", "/api/v1/uom-framework/uoms?page_size=100")
    piece = next(u["id"] for u in units if u["code"] == "PIECE")

    def product(code: str, name: str, batches: bool) -> Json:
        return dict(
            admin.call(
                "POST",
                "/api/v1/products",
                {
                    "code": code,
                    "name": name,
                    "product_type": "STOCK_ITEM",
                    "tax_profile_group_code": "GST_12_LOCAL",
                    "selling_price": "100",
                    "purchase_price": "60",
                    "base_uom_id": piece,
                    "inventory_uom_id": piece,
                    "sales_uom_id": piece,
                    "purchase_uom_id": piece,
                    "track_batch": batches,
                    "track_expiry": batches,
                },
            )
        )

    amox = product(f"{tag}-AMX", f"Amoxicillin {built.suffix}", True)
    short = product(f"{tag}-SHT", f"Scarce Syrup {built.suffix}", False)
    lines: list[Json] = [
        {
            "product_id": amox["id"],
            "quantity": "10",
            "unit_cost": "60",
            "batch_number": f"{tag}-B{n}",
            "expiry_date": (today + timedelta(days=days)).isoformat(),
        }
        for n, days in ((1, -30), (2, 20), (3, 400))
    ]
    lines.append({"product_id": short["id"], "quantity": "3", "unit_cost": "60"})
    opening = admin.call(
        "POST",
        "/api/v1/inventory/opening-stock",
        {
            "warehouse_id": warehouse["id"],
            "branch_id": branch["id"],
            "reference_number": f"{tag}-OS",
            "posting_date": today.isoformat(),
            "lines": lines,
        },
    )
    admin.call("POST", f"/api/v1/inventory/opening-stock/{opening['id']}/post")
    customer = admin.call(
        "POST",
        "/api/v1/customers",
        {
            "code": f"{tag}-RX",
            "name": f"Clinic {built.suffix}",
            "customer_type": "BUSINESS",
            "currency_code": "INR",
        },
    )
    numbers = []
    for item, quantity in ((amox, "5"), (short, "10")):
        order = admin.call(
            "POST",
            "/api/v1/sales-orders",
            {
                "customer_id": customer["id"],
                "order_date": today.isoformat(),
                "warehouse_id": warehouse["id"],
                "branch_id": branch["id"],
                "lines": [
                    {
                        "line_number": 1,
                        "product_id": item["id"],
                        "quantity": quantity,
                        "unit_price": "100",
                    }
                ],
            },
        )
        admin.call("POST", f"/api/v1/sales-orders/{order['id']}/approve")
        numbers.append(order.get("order_number"))
    built.say(
        "Batched product",
        f"{tag}-AMX: {tag}-B1 (expired), -B2 (20 days), -B3 (400 days), 10 each",
    )
    built.say("Scarce product", f"{tag}-SHT: 3 on hand")
    built.say("Customer", f"{tag}-RX  (Clinic {built.suffix})")
    built.say(
        "Orders",
        f"{numbers[0]} for 5 {tag}-AMX; {numbers[1]} for 10 {tag}-SHT; both approved",
    )


def build_electronics_firm(built: Built) -> None:
    """Make an Electronics firm of this run's own with serialised stock."""
    admin = _own_trading_firm(built, "E", "Electronics", "ELECTRONICS")
    tag = built.suffix.upper()
    today = date.today()
    warehouse = by_code(admin, "/api/v1/warehouses", "MAIN")
    branch = by_code(admin, "/api/v1/branches", "HO")
    units = admin.call("GET", "/api/v1/uom-framework/uoms?page_size=100")
    piece = next(u["id"] for u in units if u["code"] == "PIECE")
    mixer = admin.call(
        "POST",
        "/api/v1/products",
        {
            "code": f"{tag}-MIX",
            "name": f"Mixer Grinder {built.suffix}",
            "product_type": "STOCK_ITEM",
            "tax_profile_group_code": "GST_18_LOCAL",
            "base_uom_id": piece,
            "inventory_uom_id": piece,
            "sales_uom_id": piece,
            "purchase_uom_id": piece,
            "track_serial": True,
        },
    )
    opening = admin.call(
        "POST",
        "/api/v1/inventory/opening-stock",
        {
            "warehouse_id": warehouse["id"],
            "branch_id": branch["id"],
            "reference_number": f"{tag}-OS",
            "posting_date": today.isoformat(),
            "lines": [
                {"product_id": mixer["id"], "quantity": "5", "unit_cost": "2000"}
            ],
        },
    )
    admin.call("POST", f"/api/v1/inventory/opening-stock/{opening['id']}/post")
    for n in range(1, 6):
        admin.call(
            "POST",
            "/api/v1/batch-serial/serials",
            {
                "product_id": mixer["id"],
                "warehouse_id": warehouse["id"],
                "branch_id": branch["id"],
                "serial_number": f"{tag}-MIX-{n:04d}",
                "warranty_start": today.isoformat(),
                "warranty_end": (today + timedelta(days=365)).isoformat(),
                "current_owner": None,
                "asset_reference": None,
            },
        )
    built.say(
        "Serialised product", f"{tag}-MIX  (Mixer Grinder {built.suffix}), 5 on hand"
    )
    built.say("Serials", f"{tag}-MIX-0001 to -0005, warranty one year from today")


def build_selling_firm(built: Built) -> None:
    """Make a Wholesale firm of this run's own, priced the way WHOLE01 is.

    Its own store, because everything here is firm-wide: a price list ladder
    reaches every customer, a promotion every document, and TCS every
    receipt. Two customers -- one on a standing discount with no PAN, one on
    a negotiated list with a PAN -- and a detergent at 84 with 100 on hand.
    Promotions: BULK5 (7.5% on a line of 25 or more), BIGORDER (200 off a
    bill of 4,500 or more, ends the stack), CLEARANCE (1% on a line of 40 or
    more) and WELCOME (2.5%, coupon only: WELCOME10, WELCOME10B). TCS is on
    with a threshold of 0, so every receipt shows it; loyalty earns 2 points
    per 100.
    """
    admin = _own_trading_firm(built, "S", "Selling", "WHOLESALE")
    tag = built.suffix.upper()
    today = date.today()
    warehouse = by_code(admin, "/api/v1/warehouses", "MAIN")
    branch = by_code(admin, "/api/v1/branches", "HO")
    units = admin.call("GET", "/api/v1/uom-framework/uoms?page_size=100")
    piece = next(u["id"] for u in units if u["code"] == "PIECE")
    groups = {
        key: admin.call(
            "POST",
            "/api/v1/customers/groups",
            {"code": key, "name": name, "default_discount_percent": rate},
        )
        for key, name, rate in (
            ("RETAILER", "Retailer", "1.75"),
            ("WHOLESALER", "Wholesaler", "3.25"),
        )
    }
    admin.call(
        "POST",
        "/api/v1/customers",
        {
            "code": f"{tag}-C01",
            "name": f"Vijaya Stores {built.suffix}",
            "customer_type": "BUSINESS",
            "currency_code": "INR",
            "default_discount_percent": "7.5",
            "customer_group_id": groups["RETAILER"]["id"],
        },
    )
    c02 = admin.call(
        "POST",
        "/api/v1/customers",
        {
            "code": f"{tag}-C02",
            "name": f"Anand Agencies {built.suffix}",
            "customer_type": "BUSINESS",
            "currency_code": "INR",
            "customer_group_id": groups["WHOLESALER"]["id"],
            "pan_number": "ABCDE1234F",
        },
    )
    product = admin.call(
        "POST",
        "/api/v1/products",
        {
            "code": f"{tag}-DET",
            "name": f"Detergent 1kg {built.suffix}",
            "product_type": "STOCK_ITEM",
            "tax_profile_group_code": "GST_18_LOCAL",
            "selling_price": "84",
            "purchase_price": "60",
            "base_uom_id": piece,
            "inventory_uom_id": piece,
            "sales_uom_id": piece,
            "purchase_uom_id": piece,
        },
    )
    opening = admin.call(
        "POST",
        "/api/v1/inventory/opening-stock",
        {
            "warehouse_id": warehouse["id"],
            "branch_id": branch["id"],
            "reference_number": f"{tag}-OS",
            "posting_date": today.isoformat(),
            "lines": [
                {"product_id": product["id"], "quantity": "100", "unit_cost": "60"}
            ],
        },
    )
    admin.call("POST", f"/api/v1/inventory/opening-stock/{opening['id']}/post")
    ladder = [("0", "2"), ("15", "4.25"), ("18", "6.75")]
    admin.call(
        "POST",
        "/api/v1/price-lists",
        {
            "code": "STANDING",
            "name": "Standing",
            "effective_from": "2000-01-01",
            "items": [
                {"product_id": product["id"], "min_quantity": q, "discount_percent": r}
                for q, r in ladder
            ],
        },
    )
    admin.call(
        "POST",
        "/api/v1/price-lists",
        {
            "code": "NEGOTIATED",
            "name": "Negotiated",
            "customer_id": c02["id"],
            "effective_from": "2000-01-01",
            "items": [
                {
                    "product_id": product["id"],
                    "min_quantity": "0",
                    "discount_percent": "9.25",
                }
            ],
        },
    )

    def offer(
        code: str,
        priority: int,
        conditions: list[Json],
        action: Json,
        **extra: object,
    ) -> Json:
        return dict(
            admin.call(
                "POST",
                "/api/v1/promotions",
                {
                    "code": code,
                    "name": code.title(),
                    "priority": priority,
                    "status": "ACTIVE",
                    "effective_from": "2020-01-01",
                    "conditions": conditions,
                    "actions": [action],
                    **extra,
                },
            )
        )

    def at_least(field: str, number: str) -> Json:
        return {
            "field_key": field,
            "operator": "GREATER_OR_EQUAL",
            "value_number": number,
        }

    offer(
        "BULK5",
        10,
        [at_least("line_quantity", "25")],
        {"action_type": "LINE_DISCOUNT_PERCENT", "percent": "7.5"},
    )
    offer(
        "BIGORDER",
        20,
        [at_least("document_gross", "4500")],
        {"action_type": "BILL_DISCOUNT_AMOUNT", "amount": "200"},
        allow_stacking=False,
    )
    offer(
        "CLEARANCE",
        30,
        [at_least("line_quantity", "40")],
        {"action_type": "LINE_DISCOUNT_PERCENT", "percent": "1"},
    )
    welcome = offer(
        "WELCOME",
        40,
        [],
        {"action_type": "LINE_DISCOUNT_PERCENT", "percent": "2.5"},
        requires_coupon=True,
    )
    for code in ("WELCOME10", "WELCOME10B"):
        admin.call(
            "POST",
            "/api/v1/promotions/coupons",
            {"promotion_id": welcome["id"], "code": code},
        )
    admin.call(
        "PUT",
        "/api/v1/tcs/settings",
        {
            "is_enabled": True,
            "threshold_amount": "0",
            "rate_percent": "0.1",
            "rate_without_pan_percent": "1",
            "preceding_year_turnover": "150000000",
        },
    )
    admin.call(
        "PUT",
        "/api/v1/loyalty/settings",
        {
            "is_enabled": True,
            "points_per_amount": "2",
            "amount_per_point": "1",
            "minimum_redemption_points": 50,
            "expiry_months": 24,
        },
    )
    built.say(
        "Customers",
        f"{tag}-C01 Vijaya (7.5% standing, Retailer, no PAN); "
        f"{tag}-C02 Anand (Wholesaler, PAN)",
    )
    built.say(
        "Product",
        f"{tag}-DET  (Detergent 1kg {built.suffix}), 84, GST 18 local, 100 in MAIN",
    )
    built.say(
        "Price lists",
        "STANDING on DET: 0 -> 2%, 15 -> 4.25%, 18 -> 6.75%; NEGOTIATED for C02: 9.25%",
    )
    built.say(
        "Promotions",
        "BULK5 7.5% at 25+; BIGORDER 200 off 4,500+ (ends stack); CLEARANCE 1% at 40+",
    )
    built.say("Coupons", "WELCOME 2.5%, codes WELCOME10 and WELCOME10B")
    built.say("TCS", "on, threshold 0, 0.1% (1% without a PAN)")
    built.say(
        "Loyalty", "2 points per 100, worth 1, 50 to redeem, expire after 24 months"
    )


def _selling_stage(built: Built, stage: str) -> None:
    """Build selling-firm and carry one sale of Vijaya's up to a stage.

    ``ordered``: an order for 12 detergent with coupon WELCOME10, approved.
    ``delivered``: notes for 5 and 7, both dispatched. ``invoiced``: the note
    for 5 billed and approved (483.21). ``paid``: two receipts against it --
    241.60, then 341.61 with 241.61 applied -- and the note for 7 billed and
    approved.
    """
    stages = ("ordered", "delivered", "invoiced", "paid")
    build_selling_firm(built)
    firm = built.known[f"{built.suffix.upper()}-S"]
    admin = built.admin.as_user(built.admin.token or "", built.firms[firm.code])
    tag = built.suffix.upper()
    today = date.today().isoformat()
    warehouse = by_code(admin, "/api/v1/warehouses", "MAIN")
    branch = by_code(admin, "/api/v1/branches", "HO")
    c01 = admin.call("GET", f"/api/v1/customers?search={tag}-C01")[0]
    product = admin.call("GET", f"/api/v1/products?search={tag}-DET")[0]
    order = admin.call(
        "POST",
        "/api/v1/sales-orders",
        {
            "customer_id": c01["id"],
            "order_date": today,
            "warehouse_id": warehouse["id"],
            "branch_id": branch["id"],
            "coupon_code": "WELCOME10",
            "lines": [
                {
                    "line_number": 1,
                    "product_id": product["id"],
                    "quantity": "12",
                    "unit_price": "84",
                }
            ],
        },
    )
    admin.call("POST", f"/api/v1/sales-orders/{order['id']}/approve")
    built.say(
        "Sales order",
        f"{order.get('order_number')}: 12 at 84 less 2.5% (WELCOME10), approved",
    )
    if stages.index(stage) < 1:
        return
    order_line = admin.call("GET", f"/api/v1/sales-orders/{order['id']}")["lines"][0]
    notes = []
    for quantity in ("5", "7"):
        note = admin.call(
            "POST",
            "/api/v1/delivery-notes",
            {
                "sales_order_id": order["id"],
                "delivery_date": today,
                "lines": [
                    {
                        "sales_order_line_id": order_line["id"],
                        "line_number": 1,
                        "current_delivery_quantity": quantity,
                    }
                ],
            },
        )
        admin.call("POST", f"/api/v1/delivery-notes/{note['id']}/approve")
        admin.call("POST", f"/api/v1/delivery-notes/{note['id']}/dispatch")
        notes.append(note)
        built.say(
            f"Note for {quantity}", f"{note.get('delivery_note_number')}, dispatched"
        )
    if stages.index(stage) < 2:
        return

    def bill(note: Json, quantity: str) -> Json:
        line = admin.call("GET", f"/api/v1/delivery-notes/{note['id']}")["lines"][0]
        invoice = admin.call(
            "POST",
            "/api/v1/sales-invoices",
            {
                "customer_id": c01["id"],
                "branch_id": branch["id"],
                "invoice_date": today,
                "source_documents": [
                    {
                        "source_document_type": "DELIVERY_NOTE",
                        "source_document_id": note["id"],
                    }
                ],
                "lines": [
                    {
                        "source_document_type": "DELIVERY_NOTE",
                        "source_document_id": note["id"],
                        "source_document_line_id": line["id"],
                        "line_number": 1,
                        "current_invoice_quantity": quantity,
                    }
                ],
            },
        )
        return dict(
            admin.call("POST", f"/api/v1/sales-invoices/{invoice['id']}/approve")
        )

    first = bill(notes[0], "5")
    built.say("Invoice for 5", f"{first.get('invoice_number')}, approved, 483.21")
    if stages.index(stage) < 3:
        return
    for amount, applied in (("241.60", "241.60"), ("341.61", "241.61")):
        receipt = admin.call(
            "POST",
            "/api/v1/receipts",
            {
                "party_id": c01["id"],
                "settlement_date": today,
                "amount": amount,
                "method": "BANK",
                "allocations": [{"invoice_id": first["id"], "amount": applied}],
            },
        )
        built.say(
            f"Receipt of {amount}",
            f"{receipt.get('settlement_number')}, {applied} applied",
        )
    second = bill(notes[1], "7")
    built.say("Invoice for 7", f"{second.get('invoice_number')}, approved")


def build_selling_ordered(built: Built) -> None:
    """Make selling-firm with Vijaya's order for 12 approved."""
    _selling_stage(built, "ordered")


def build_selling_delivered(built: Built) -> None:
    """Make selling-ordered with both notes, 5 and 7, dispatched."""
    _selling_stage(built, "delivered")


def build_selling_invoiced(built: Built) -> None:
    """Make selling-delivered with the note for 5 billed and approved."""
    _selling_stage(built, "invoiced")


def build_selling_paid(built: Built) -> None:
    """Make selling-invoiced with two receipts and the note for 7 billed."""
    _selling_stage(built, "paid")


#: Every fixture, what it builds, and the cases that name it.
FIXTURES: dict[str, tuple[str, Callable[[Built], None], str]] = {
    "firm-admin": (
        "A fresh firm administrator of TEST01.",
        build_firm_admin,
        "TC-ROLE-001..004, TC-PLAT-005, TC-ME-007, TC-FIRM-016, "
        "TC-TMPL-001..004, TC-TMPL-011, TC-TMPL-015, TC-USER-003, TC-USER-004, "
        "TC-USER-009, TC-GRANT-002..004, TC-GRANT-006, TC-GRANT-008, TC-CASH-004, "
        "TC-AUDIT-003, TC-AUDIT-005, TC-LOOK-005, TC-SESS-002, TC-SESS-006, "
        "TC-ISO-004, TC-CONF-001..003, TC-CONF-005",
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
        "TC-PLAT-001..003, TC-ME-006, TC-FIRM-001..003, TC-TMPL-012, "
        "TC-USER-005, TC-RTIER-005, TC-AUDIT-001, TC-AUDIT-002",
    ),
    "platform-admin-member": (
        "An ALL_FIRMS platform administrator who belongs to both test firms.",
        build_platform_admin_member,
        "TC-PLAT-004, TC-SESS-010",
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
        "TC-TMPL-009, TC-GRANT-007, TC-AUDIT-006, TC-LOOK-005, TC-CONF-001",
    ),
    "manual-hire": (
        "firm-admin + a TEST01 user with two roles picked by hand.",
        build_manual_hire,
        "TC-TMPL-005, TC-USER-001, TC-AUDIT-004",
    ),
    "two-tier-hire": (
        "firm-admin + platform-admin + a user with roles in both tiers.",
        build_two_tier_hire,
        "TC-TMPL-006..008, TC-RTIER-007",
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
    "template-offering": (
        "firm-admin + platform-admin: one writes templates, one reads them.",
        build_template_offering,
        "TC-TMPL-013, TC-TMPL-014, TC-LOOK-007",
    ),
    "shared-member": (
        "firm-admin + platform-admin + a TEST01/TEST02 user + a TEST02-only one.",
        build_shared_member,
        "TC-USER-002, TC-USER-006..008, TC-RTIER-001, TC-RTIER-008, TC-SESS-010",
    ),
    "shared-member-roles": (
        "shared-member, with Shared Member holding a role in each tier.",
        build_shared_member_roles,
        "TC-RTIER-002..004, TC-RTIER-006",
    ),
    "invoiced": (
        "firm-admin + a sale of this run's own: order, note, approved invoice.",
        build_invoiced,
        "TC-GRANT-001, TC-ISO-003",
    ),
    "loyalty-viewer": (
        "A TEST01 SALES_MANAGER: reads the loyalty scheme, cannot change it.",
        build_loyalty_viewer,
        "TC-GRANT-005",
    ),
    "cashier": (
        "A TEST01 user holding CASHIER alone, and a customer to take money from.",
        build_cashier,
        "TC-CASH-001, TC-CASH-002",
    ),
    "accountant": (
        "A TEST01 user holding ACCOUNTANT alone.",
        build_accountant,
        "TC-CASH-003",
    ),
    "outsider": (
        "firm-admin + platform-admin + a TEST02-only cashier TEST01 can hire.",
        build_outsider,
        "TC-LOOK-001, TC-LOOK-002, TC-LOOK-006",
    ),
    "outsider-added": (
        "outsider, already added to TEST01 as Counter Sales.",
        build_outsider_added,
        "TC-LOOK-003, TC-LOOK-004",
    ),
    "lock-target": (
        "firm-admin + platform-admin + an ordinary TEST01 user to act on.",
        build_lock_target,
        "TC-SESS-003..005, TC-SESS-007..009, TC-SESS-011",
    ),
    "isolation-pair": (
        "platform-admin + a customer of this run's own in each test firm.",
        build_isolation_pair,
        "TC-SESS-001, TC-ISO-002",
    ),
    "shared-isolation-pair": (
        "platform-admin + a customer of this run's own in TESTSH1 and TESTSH2.",
        build_shared_isolation_pair,
        "TC-ISO-001",
    ),
    "customer-master": (
        "firm-admin + seller + a fully described customer, segments, places.",
        build_customer_master,
        "TC-CUST-001..004, TC-CUST-006",
    ),
    "invoiced-part-paid": (
        "invoiced, with 200 of the 590 invoice collected.",
        build_invoiced_part_paid,
        "TC-CUST-005",
    ),
    "vendor-master": (
        "firm-admin + a TEST01 vendor with every child collection.",
        build_vendor_master,
        "TC-MAST-001, TC-MAST-002",
    ),
    "product-master": (
        "firm-admin + a TEST01 product with every slot and a Case barcode.",
        build_product_master,
        "TC-MAST-003, TC-MAST-008",
    ),
    "branch-master": (
        "A TEST02 admin, a default branch and warehouse, and two import files.",
        build_branch_master,
        "TC-MAST-004..007",
    ),
    "config-firm": (
        "ready-firm + a vendor and a product with its own PACK->KG rule.",
        build_config_firm,
        "TC-CONF-004, TC-CONF-006",
    ),
    "buy-ready": (
        "firm-admin + a vendor and a product with nothing on hand.",
        build_buy_ready,
        "TC-BUY-001",
    ),
    "po-approved": (
        "buy-ready + an approved purchase order for 10 at 100.",
        build_po_approved,
        "TC-BUY-002, TC-BUY-003, TC-BUY-007",
    ),
    "po-received": (
        "po-approved + receipts of 4 and 6, both completed.",
        build_po_received,
        "TC-BUY-004, TC-BUY-006, TC-STOCK-001",
    ),
    "po-invoiced": (
        "po-received + an approved supplier invoice for the receipt of 6.",
        build_po_invoiced,
        "TC-BUY-005, TC-BUY-008",
    ),
    "stock-ready": (
        "firm-admin + 50 of a product in MAIN + an empty second warehouse.",
        build_stock_ready,
        "TC-STOCK-002..004",
    ),
    "pharma-firm": (
        "A Pharmacy firm of the run's own: batches, expiries, two orders.",
        build_pharma_firm,
        "TC-STOCK-005..007",
    ),
    "electronics-firm": (
        "An Electronics firm of the run's own: a serialised product.",
        build_electronics_firm,
        "TC-STOCK-008",
    ),
    "selling-firm": (
        "A Wholesale firm of the run's own priced like WHOLE01: lists, offers, TCS.",
        build_selling_firm,
        "TC-SELL-001..006",
    ),
    "selling-ordered": (
        "selling-firm + Vijaya's order for 12 (coupon WELCOME10), approved.",
        build_selling_ordered,
        "TC-SELL-007..009, TC-SELL-017",
    ),
    "selling-delivered": (
        "selling-ordered + notes for 5 and 7, dispatched.",
        build_selling_delivered,
        "TC-SELL-010, TC-SELL-011",
    ),
    "selling-invoiced": (
        "selling-delivered + the note for 5 billed and approved.",
        build_selling_invoiced,
        "TC-SELL-012, TC-SELL-013, TC-SELL-015, TC-SELL-016",
    ),
    "selling-paid": (
        "selling-invoiced + receipts of 241.60 and 341.61 + the 7 billed.",
        build_selling_paid,
        "TC-SELL-014",
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
