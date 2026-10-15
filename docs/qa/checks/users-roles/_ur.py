"""Helpers the users-roles checks share (not a check; run.py skips it).

Accounts (see setup.py): ``admin`` is a Firm admin of TEST01, ``platform`` a
platform administrator who belongs to no firm, ``seller`` a Field Sales user
of TEST01. Firm ``one`` is TEST01 and firm ``two`` TEST02. Every user, role
and template a check needs it makes itself under a fresh tag and retires in a
``finally``, so a check runs alone and runs twice. Passwords are 12+ chars and
users are made with ``force_password_change`` off unless the case is about it
(a user who must change the password is refused every route until they do).
"""

from __future__ import annotations

import pathlib
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from common import Api, Check, all_rows, client, data, fetch, message, sign_in, state, suffix  # noqa: E402,F401

MODULE = "users-roles"
PW = "Welcome@12345x"
U = "/api/v1/users"
R = "/api/v1/roles"
T = "/api/v1/user-templates"
BAD_ID = "11111111-1111-1111-1111-111111111111"


def api(which: str = "admin") -> Api:
    """Return a signed-in account of the users-roles state."""
    return client(which, MODULE)


def one() -> str:
    """Return the id of TEST01."""
    return str(state(MODULE)["one"])


def two() -> str:
    """Return the id of TEST02."""
    return str(state(MODULE)["two"])


def tag(n: int = 5) -> str:
    """Return a fresh upper-case tag."""
    return suffix(n)


def must(answer: tuple[int, Any], what: str, ok: tuple[int, ...] = (200, 201, 204)) -> Any:  # noqa: ANN401
    """Return the data of a good answer, or stop saying what was refused."""
    status, body = answer
    if status not in ok:
        raise SystemExit(f"PRECONDITION {what}: {status} {message(body)[:300]}")
    return data(body)


def assignment(firm_id: str, primary: bool = False) -> dict:
    """Return one membership assignment."""
    return {"firm_id": firm_id, "is_primary": primary, "is_active": True}


class Scene:
    """Hold what one check made and retire it again.

    ``user`` makes an account through the platform administrator (so it can
    sit in any firms) and ``cleanup`` soft-deletes it; roles and templates are
    deleted by whoever made them.
    """

    def __init__(self) -> None:
        self.tag = tag()
        self.admin = api("admin")
        self.platform = api("platform")
        self.users: list[str] = []
        self.roles: list[tuple[Api, str]] = []
        self.templates: list[tuple[Api, str]] = []
        self._roles: dict[str, str] = {}
        self._templates: dict[str, dict] = {}

    # lookups -------------------------------------------------------------
    def role_id(self, code: str) -> str:
        """Return the id of a seeded role (read as the platform administrator)."""
        if not self._roles:
            for row in all_rows(self.platform, "/api/v1/roles"):
                if row.get("firm_id") is None:
                    self._roles[row["code"]] = str(row["id"])
        return self._roles[code]

    def role_code(self, role_id: str) -> str:
        """Return the code of a seeded role id (or the id itself)."""
        self.role_id("FIRM_ADMIN")
        back = {v: k for k, v in self._roles.items()}
        return back.get(role_id, role_id)

    def template(self, code: str) -> dict:
        """Return a seeded job template by its code."""
        if not self._templates:
            for row in all_rows(self.platform, "/api/v1/user-templates"):
                self._templates[row["code"]] = row
        return self._templates[code]

    # makers --------------------------------------------------------------
    def user(
        self,
        name: str,
        firms: tuple[str, ...] | None = None,
        *,
        force: bool = False,
        by: Api | None = None,
    ) -> dict:
        """Create an account in these firms (TEST01 by default); return its row."""
        firms = (one(),) if firms is None else firms
        maker = by or self.platform
        email = f"{name}.{self.tag}@qa.test".lower()
        row = must(
            maker.post(U, {"email": email, "full_name": f"{name} {self.tag}",
                           "password": PW, "force_password_change": force}),
            f"create user {name}",
        )
        self.users.append(str(row["id"]))
        if firms:
            must(self.platform.put(f"{U}/{row['id']}/firms",
                                   {"assignments": [assignment(f, i == 0) for i, f in enumerate(firms)]}),
                 f"place {name}")
        row["email"] = email
        return row

    def sign_in(self, row: dict, firm: str | None = None) -> Api:
        """Sign in as an account made by ``user``."""
        return sign_in(row["email"], PW, firm if firm is not None else one())

    def hire(self, name: str, template_code: str, firm: str | None = None) -> tuple[dict, Api]:
        """Create a TEST01 user, apply a seeded job as the firm admin, sign in."""
        row = self.user(name, (firm or one(),))
        must(self.admin.post(f"{U}/{row['id']}/apply-template",
                             {"template_id": self.template(template_code)["id"]}), f"apply {template_code}")
        return row, self.sign_in(row, firm)

    def role(self, by: Api, code: str | None = None, **extra: Any) -> dict:  # noqa: ANN401
        """Create a custom role as ``by`` and remember it for cleanup."""
        code = code or f"qa-{self.tag.lower()}-{len(self.roles)}"
        row = must(by.post(R, {"code": code, "name": f"QA role {self.tag}", **extra}), "role")
        self.roles.append((by, str(row["id"])))
        return row

    def new_template(self, by: Api, role_ids: list[str], code: str | None = None, **extra: Any) -> dict:  # noqa: ANN401
        """Create a job template as ``by`` and remember it for cleanup."""
        code = code or f"qa-{self.tag.lower()}-t{len(self.templates)}"
        row = must(by.post(T, {"code": code, "name": f"QA job {self.tag}", "role_ids": role_ids, **extra}), "template")
        self.templates.append((by, str(row["id"])))
        return row

    def cleanup(self) -> None:
        """Retire what the check made; a failure here is not the check's."""
        for by, tid in self.templates:
            by.delete(f"{T}/{tid}")
        for by, rid in self.roles:
            by.delete(f"{R}/{rid}")
        for uid in self.users:
            self.platform.delete(f"{U}/{uid}")


def roles_of(api_: Api, user_id: str, firm_id: str) -> list[str]:
    """Return the ids of the roles a user holds in one firm (as ``api_``)."""
    return sorted(data(api_.get(f"{U}/{user_id}/firms/{firm_id}/roles")[1])["ids"])


def global_roles_of(api_: Api, user_id: str) -> list[str]:
    """Return the ids of the roles a user holds in every firm."""
    return sorted(data(api_.get(f"{U}/{user_id}/global-roles")[1])["ids"])


def shared(sc: Scene, name: str = "shared") -> dict:
    """Make a user in TEST02 (primary) and TEST01, like the fixture Shared Member."""
    return sc.user(name, (two(), one()))


def outsider(sc: Scene, name: str = "outsider") -> dict:
    """Make a TEST02-only CASHIER, like the fixture Outsider."""
    row = sc.user(name, (two(),))
    must(sc.platform.put(f"{U}/{row['id']}/firms/{two()}/roles", {"ids": [sc.role_id("CASHIER")]}), "outsider role")
    return row


def set_firm_roles(sc: Scene, user_id: str, firm_id: str, role_codes: list[str], by: Api | None = None) -> None:
    """Set a user seeded roles in one firm (as the platform admin by default)."""
    must((by or sc.platform).put(f"{U}/{user_id}/firms/{firm_id}/roles",
                                 {"ids": [sc.role_id(x) for x in role_codes]}), "firm roles")


def set_global_roles(sc: Scene, user_id: str, role_codes: list[str]) -> None:
    """Set a user seeded roles in every firm (as the platform admin)."""
    must(sc.platform.put(f"{U}/{user_id}/roles", {"ids": [sc.role_id(x) for x in role_codes]}), "global roles")


def codes(sc: Scene, ids: list[str]) -> list[str]:
    """Return sorted role codes for some seeded role ids."""
    return sorted(sc.role_code(i) for i in ids)


#: One write route per permission code, each sent an empty body. The server
#: checks the permission before it reads the body, so a job that holds the code
#: gets 422 (the body is wrong) and a job that lacks it gets 403 -- no record is
#: ever created. (path, method, the code(s) that open it)
WRITES = {
    "customers": ("POST", "/api/v1/customers"),  # CUSTOMER_CREATE
    "vendors": ("POST", "/api/v1/vendors"),  # VENDOR_CREATE
    "receipts": ("POST", "/api/v1/receipts"),  # RECEIPT_CREATE
    "payments": ("POST", "/api/v1/payments"),  # PAYMENT_CREATE
    "quotations": ("POST", "/api/v1/quotations"),  # SALES_QUOTATION_CREATE
    "sales-orders": ("POST", "/api/v1/sales-orders"),  # SALES_ORDER_CREATE
    "sales-invoices": ("POST", "/api/v1/sales-invoices"),  # SALES_INVOICE_CREATE
    "expenses": ("POST", "/api/v1/expenses"),  # EXPENSE_CREATE
    "credit-notes": ("POST", "/api/v1/credit-notes"),  # CREDIT_NOTE_MANAGE
    "delivery-notes": ("POST", "/api/v1/delivery-notes"),  # DELIVERY_NOTE_CREATE
    "inventory-adjustments": ("POST", "/api/v1/inventory/adjustments"),  # INVENTORY_ADJUST
    "journal-entries": ("POST", "/api/v1/finance/journal-entries"),  # JOURNAL_CREATE
    "purchases": ("POST", "/api/v1/purchases"),  # PURCHASE_CREATE
    "rfqs": ("POST", "/api/v1/rfqs"),  # RFQ_MANAGE
    "roles": ("POST", "/api/v1/roles"),  # ROLE_CREATE
    "customer-update": ("PUT", f"/api/v1/customers/{BAD_ID}"),  # CUSTOMER_UPDATE
}


def job_check(name: str, template_code: str, allowed: list[str], refused: list[str], platform_part: bool = False) -> None:
    """Hire one user into a seeded job and check the server agrees with the menu table.

    ``allowed`` writes must not be refused (422/404, not 403); ``refused`` writes must
    be 403 with the standard message. Unless ``platform_part``, the people screens
    (users, roles, permissions, templates) are refused as well.
    """
    c = Check(name)
    sc = Scene()
    try:
        row, u = sc.hire(template_code.replace("-", "")[:10], template_code)
        for key in allowed:
            method, path = WRITES[key]
            st, body = u.call(method, path, {})
            c.ok(st in (404, 422), f"{template_code} may {key} (not refused)", (st, message(body)))
        for key in refused:
            method, path = WRITES[key]
            c.refused(u.call(method, path, {}), 403, "You do not have permission", f"{template_code} may not {key}")
        if not platform_part:
            for path in (U, R, "/api/v1/permissions", T):
                c.eq(u.get(path)[0], 403, f"{template_code}: no Platform part, GET {path}")
        c.eq(u.post("/api/v1/firms", {})[0], 403, f"{template_code}: creating a firm is platform-only")
    finally:
        sc.cleanup()
    c.done()
