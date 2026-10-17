# ruff: noqa: E501, ANN401, SIM905
# A drive script: long sentences in case details, JSON bodies typed as Any, and
# field lists written as words are all deliberate here.
"""Drive the bill-series-by-company cases over HTTP on a firm of its own.

    ./.venv/Scripts/python.exe scripts/drive_bill_series.py

Item 29(e), backlog 157, design ``docs/design/BILL_SERIES_BY_COMPANY_DESIGN.md``
section 11. Makes (or finds) the firm ``BSER1017``, provisions and finishes it
through the firm set-up endpoints, makes a firm admin for it, then drives each
case against the running backend and prints PASS or FAIL per case. Re-runnable:
every record is found by code first, and the cases make their own bills.

The loop admin's sign-in is read at run time from the file named by
``BSER_ADMIN_FILE`` (default ``D:/ws/agencyApp/unattended/loop_admin.txt``,
``email=`` and ``password=`` lines). It is never printed or stored here.
Standard library only; set ``QA_BASE`` to point at another server.
"""

from __future__ import annotations

import http.client
import json
import os
import pathlib
import re
import sys
import urllib.parse
from datetime import UTC, datetime, timedelta
from typing import Any

BASE = os.environ.get("QA_BASE", "http://127.0.0.1:8000")
ADMIN_FILE = pathlib.Path(
    os.environ.get("BSER_ADMIN_FILE", r"D:/ws/agencyApp/unattended/loop_admin.txt")
)
FIRM_CODE = "BSER1017"
FIRM_ADMIN = "bser1017.admin@fixtures.local"
#: A fixture password for the throwaway firm admin, not a real credential.
FIRM_ADMIN_PASSWORD = "Fixture@2026pw"  # noqa: S105
SI = "/api/v1/sales-invoices"
SR = "/api/v1/sales-returns"
SETTING = "/api/v1/document-framework/bill-series-settings"
Answer = tuple[int, Any]


class Api:
    """One signed-in user, optionally inside one firm."""

    def __init__(self, token: str | None = None, firm_id: str | None = None) -> None:
        """Hold the bearer token and the firm header."""
        self.token = token
        self.firm_id = firm_id

    def call(self, method: str, path: str, body: Any = None) -> Answer:
        """Send JSON and return (status, decoded answer)."""
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.firm_id:
            headers["X-Firm-ID"] = self.firm_id
        raw = None if body is None else json.dumps(body).encode("utf-8")
        url = urllib.parse.urlsplit(BASE)
        conn = http.client.HTTPConnection(
            url.hostname or "127.0.0.1", url.port, timeout=600
        )
        try:
            conn.request(method, path, body=raw, headers=headers)
            reply = conn.getresponse()
            text = reply.read()
        finally:
            conn.close()
        try:
            return reply.status, json.loads(text.decode("utf-8")) if text else None
        except ValueError:
            return reply.status, text

    def get(self, path: str) -> Answer:
        """GET."""
        return self.call("GET", path)

    def post(self, path: str, body: Any = None) -> Answer:
        """POST."""
        return self.call("POST", path, {} if body is None else body)

    def put(self, path: str, body: Any = None) -> Answer:
        """PUT."""
        return self.call("PUT", path, {} if body is None else body)


def data(answer: Answer) -> Any:  # noqa: ANN401
    """Return the ``data`` of an answer."""
    body = answer[1]
    return body.get("data", body) if isinstance(body, dict) else body


def said(answer: Answer) -> str:
    """Return what the server said, for a refusal."""
    body = answer[1]
    if not isinstance(body, dict):
        return str(body)[:300]
    error = body.get("error") or {}
    return f"{error.get('message') or body.get('message') or body.get('detail')} " + (
        json.dumps(error.get("details"))[:300] if error.get("details") else ""
    )


def must(answer: Answer, what: str) -> Any:  # noqa: ANN401
    """Return the data of a 2xx answer or stop saying what was refused."""
    if answer[0] not in (200, 201):
        raise SystemExit(f"PRECONDITION {what}: {answer[0]} {said(answer)}")
    return data(answer)


def rows(answer: Answer, what: str) -> list[dict]:
    """Return a list answer's rows."""
    got = must(answer, what)
    return got if isinstance(got, list) else []


def today() -> str:
    """Return the firm's business day (India) as the server judges it."""
    return (datetime.now(UTC) + timedelta(hours=5, minutes=30)).date().isoformat()


def read_admin() -> tuple[str, str]:
    """Read the loop admin's sign-in from its file; never echo it."""
    values: dict[str, str] = {}
    for line in ADMIN_FILE.read_text(encoding="utf-8-sig").splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            values[key.strip().lower()] = value.strip()
    return values["email"], values["password"]


def sign_in(email: str, password: str) -> Api:
    """Sign in once (never retried: repeated failures lock the account)."""
    status, body = Api().post(
        "/api/v1/auth/login", {"email": email, "password": password}
    )
    if status != 200:
        raise SystemExit(f"SIGN-IN REFUSED for {email}: {status}")
    return Api(str(body["data"]["access_token"]))


# -- set-up -------------------------------------------------------------------
def build_firm(platform: Api) -> str:
    """Find or make BSER1017, provision it and finish it; return its id."""
    found = rows(
        platform.get(f"/api/v1/firms?search={FIRM_CODE}&page_size=10"), "firms"
    )
    row = next((r for r in found if r.get("code") == FIRM_CODE), None)
    if row is None:
        print(f"  creating {FIRM_CODE}")
        row = must(
            platform.post(
                "/api/v1/firms",
                {
                    "name": "Bill series drive 2026-10-17",
                    "code": FIRM_CODE,
                    "country": "IN",
                    "currency_code": "INR",
                    "financial_year_start": "2026-04-01",
                    "deployment_mode": "SCHEMA",
                    "schema_name": "firm_bser1017",
                    "notes": "Built by scripts/drive_bill_series.py. Test data only.",
                },
            ),
            "create firm",
        )
    firm_id = str(row["id"])
    if not row.get("provisioned_at"):
        print("  provisioning (runs the migrations)")
        must(platform.post(f"/api/v1/firms/{firm_id}/provision"), "provision")
    ready = must(platform.get(f"/api/v1/firms/{firm_id}/readiness"), "readiness")
    steps = {s["key"]: s["status"] for s in ready["steps"]}
    base = f"/api/v1/firms/{firm_id}"
    for key, path, body in (
        ("books", "open-books", {}),
        ("tax", "apply-tax-template", {}),
        ("branches", "create-default-branch", None),
    ):
        if steps.get(key) != "DONE":
            print(f"  {key}: {path}")
            must(platform.post(f"{base}/{path}", body), path)
    ready = must(platform.get(f"/api/v1/firms/{firm_id}/readiness"), "readiness")
    if not ready["can_post"]:
        missing = [s["label"] for s in ready["steps"] if s["status"] != "DONE"]
        raise SystemExit(f"{FIRM_CODE} still cannot post. Missing: {missing}")
    return firm_id


def firm_admin(platform: Api, firm_id: str) -> Api:
    """Make the firm's own admin once and return it signed in inside the firm."""
    found = rows(
        platform.get(f"/api/v1/users?search={FIRM_ADMIN}&page_size=10"), "users"
    )
    user = next((u for u in found if u.get("email") == FIRM_ADMIN), None)
    if user is None:
        user = must(
            platform.post(
                "/api/v1/users",
                {
                    "email": FIRM_ADMIN,
                    "full_name": "Bill series firm admin",
                    "password": FIRM_ADMIN_PASSWORD,
                    "is_active": True,
                    "force_password_change": False,
                },
            ),
            "user",
        )
        must(
            platform.put(
                f"/api/v1/users/{user['id']}/firms",
                {
                    "assignments": [
                        {"firm_id": firm_id, "is_primary": True, "is_active": True}
                    ]
                },
            ),
            "membership",
        )
        roles = rows(
            platform.__class__(platform.token, firm_id).get(
                "/api/v1/roles?search=FIRM_ADMIN&page_size=50"
            ),
            "roles",
        )
        role = next(r for r in roles if r["code"] == "FIRM_ADMIN")
        must(
            platform.put(
                f"/api/v1/users/{user['id']}/firms/{firm_id}/roles",
                {"ids": [role["id"]]},
            ),
            "role",
        )
    api = sign_in(FIRM_ADMIN, FIRM_ADMIN_PASSWORD)
    api.firm_id = firm_id
    return api


class World:
    """The firm's masters: companies, products, customer, branch, warehouse."""

    def __init__(self, api: Api) -> None:
        """Find or make everything the cases bill."""
        self.api = api
        self.branch = self.find("/api/v1/branches", "HO")
        self.warehouse = self.find("/api/v1/warehouses", "MAIN")
        self.piece = next(
            u["id"]
            for u in rows(api.get("/api/v1/uom-framework/uoms?page_size=100"), "uoms")
            if u["code"] == "PIECE"
        )
        self.principals = {
            "NOPFX": self.principal("NOPFX", "No prefix company (test)", None)
        }
        self.products = {"N1": self.product("N1", "NOPFX")}
        self.customer = self.customer_row()
        self.only_one_series()
        self.layout()
        self.principals["ASIAN"] = self.principal(
            "ASIAN", "Asian Paints (test)", "ASIAN"
        )
        self.principals["PIDI"] = self.principal("PIDI", "Pidilite (test)", "PIDI")
        self.products["A1"] = self.product("A1", "ASIAN")
        self.products["A2"] = self.product("A2", "ASIAN")
        self.products["P1"] = self.product("P1", "PIDI")
        self.service = self.product("SV", "ASIAN", product_type="SERVICE")

    def layout(self) -> None:
        """Birth the sales-bill series with a first bill, then pad to 4 digits.

        A new firm has no series until its first bill, and the default pads to
        six digits, which leaves room for a three-letter prefix only. The
        design's five-letter prefix needs four, so the rule is narrowed here,
        which is also how a firm makes room.
        """
        api = self.api
        listing = "/api/v1/document-framework/document-types?page_size=100"
        found = next(
            (
                t
                for t in rows(api.get(listing), "types")
                if t["code"] == "SALES_INVOICE"
            ),
            None,
        )
        if found is None:
            approved(self, bill(self, ["N1"]))
            found = next(
                t
                for t in rows(api.get(listing), "types")
                if t["code"] == "SALES_INVOICE"
            )
        path = (
            f"/api/v1/document-framework/numbering-rules?document_type_id={found['id']}"
        )
        rule = rows(api.get(path), "rules")[0]
        self.general = str(rule["prefix"])
        if rule["sequence_padding"] != 4:
            keep = (
                "document_type_id code name prefix suffix separator include_financial_year "
                "short_financial_year include_branch_code include_company_code auto_reset "
                "manual_allowed format_pattern is_default is_active"
            ).split()
            body = {k: rule[k] for k in keep}
            body["sequence_padding"] = 4
            must(
                api.put(
                    f"/api/v1/document-framework/numbering-rules/{rule['id']}", body
                ),
                "narrow the padding",
            )

    def find(self, path: str, code: str) -> dict:
        """Return the row with this code."""
        for row in rows(self.api.get(f"{path}?search={code}&page_size=100"), path):
            if row.get("code") == code:
                return row
        raise SystemExit(f"PRECONDITION no {code} at {path}")

    def principal(self, code: str, name: str, prefix: str | None) -> dict:
        """Find or make a company; set its prefix when it differs."""
        found = next(
            (
                p
                for p in rows(self.api.get("/api/v1/products/principals"), "principals")
                if p["code"] == code
            ),
            None,
        )
        body = {"code": code, "name": name}
        if prefix is not None:
            body["bill_series_prefix"] = prefix
        if found is None:
            return must(
                self.api.post("/api/v1/products/principals", body), f"principal {code}"
            )
        if prefix is not None and found.get("bill_series_prefix") != prefix:
            return must(
                self.api.put(f"/api/v1/products/principals/{found['id']}", body),
                f"principal {code}",
            )
        return found

    def brand(self, key: str) -> str:
        """Find or make the brand of a company; return its id."""
        name = f"{key} brand"
        brands = rows(self.api.get("/api/v1/products/brands"), "brands")
        kept = next((b for b in brands if b["name"] == name), None)
        if kept is not None:
            return str(kept["id"])
        made = must(
            self.api.post(
                "/api/v1/products/brands",
                {"name": name, "principal_id": self.principals[key]["id"]},
            ),
            "brand",
        )
        return str(made["id"])

    def product(self, tag: str, company: str, product_type: str = "STOCK_ITEM") -> dict:
        """Find or make a 100.00 item at 18% and stock it in MAIN."""
        code = f"BS{tag}"
        found = rows(
            self.api.get(f"/api/v1/products?search={code}&page_size=20"), "products"
        )
        row = next((p for p in found if p.get("code") == code), None)
        if row is not None:
            return row
        made = must(
            self.api.post(
                "/api/v1/products",
                {
                    "code": code,
                    "name": f"Bill series item {tag}",
                    "brand_id": self.brand(company),
                    "product_type": product_type,
                    "tax_profile_group_code": "GST_18_LOCAL",
                    "selling_price": "100",
                    "purchase_price": "60",
                    "base_uom_id": self.piece,
                    "inventory_uom_id": self.piece,
                    "sales_uom_id": self.piece,
                    "purchase_uom_id": self.piece,
                },
            ),
            f"product {code}",
        )
        if product_type == "STOCK_ITEM":
            stocked = must(
                self.api.post(
                    "/api/v1/inventory/opening-stock",
                    {
                        "branch_id": self.branch["id"],
                        "warehouse_id": self.warehouse["id"],
                        "reference_number": f"OS-{code}",
                        "posting_date": today(),
                        "lines": [
                            {
                                "product_id": made["id"],
                                "quantity": "500",
                                "unit_cost": "60",
                            }
                        ],
                    },
                ),
                "opening stock",
            )
            must(
                self.api.post(
                    f"/api/v1/inventory/opening-stock/{stocked['id']}/post", {}
                ),
                "post stock",
            )
        return made

    def customer_row(self) -> dict:
        """Find or make the business customer."""
        found = rows(
            self.api.get("/api/v1/customers?search=BSCUST&page_size=10"), "customers"
        )
        row = next((c for c in found if c.get("code") == "BSCUST"), None)
        if row is not None:
            return row
        return must(
            self.api.post(
                "/api/v1/customers",
                {
                    "code": "BSCUST",
                    "name": "Bill series buyer",
                    "customer_type": "BUSINESS",
                    "currency_code": "INR",
                },
            ),
            "customer",
        )

    def only_one_series(self) -> None:
        """Turn the order and delivery-note stages off so a bill stands alone."""
        path = "/api/v1/sales-orders/workflow-settings"
        held = must(self.api.get(path), "workflow settings")
        keys = (
            "quotation_stage sales_order_stage delivery_note_stage default_branch_id "
            "default_warehouse_id promotion_mode max_line_discount_percent "
            "rate_includes_tax new_outlets_need_approval reservation_lapse_days "
            "sales_order_approval delivery_note_approval sales_invoice_approval "
            "round_bills_to_rupee salesman_required box_and_piece_entry"
        ).split()
        wanted = {k: held[k] for k in keys if k in held}
        wanted.update(sales_order_stage=False, delivery_note_stage=False)
        must(self.api.put(path, wanted), "workflow settings changed")


# -- the cases ----------------------------------------------------------------
RESULTS: list[tuple[str, bool, str]] = []


def record(case: str, ok: bool, detail: str = "") -> None:
    """Keep and print one case's result."""
    RESULTS.append((case, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {case}" + (f"  -- {detail}" if detail else ""))


def set_driver(api: Api, driver: str) -> None:
    """Switch the firm's series setting."""
    must(api.put(SETTING, {"series_driver": driver}), f"driver {driver}")


def bill(
    w: World, keys: list[str], freight: str | None = None, service: bool = False
) -> dict:
    """Create and approve a counter bill of one piece per product key."""
    lines = []
    for n, key in enumerate(keys, start=1):
        lines.append(
            {
                "line_number": n,
                "product_id": w.products[key]["id"],
                "current_invoice_quantity": "1",
                "warehouse_id": w.warehouse["id"],
            }
        )
    if service:
        lines.append(
            {
                "line_number": len(lines) + 1,
                "product_id": w.service["id"],
                "current_invoice_quantity": "1",
                "warehouse_id": w.warehouse["id"],
            }
        )
    body: dict[str, Any] = {
        "customer_id": w.customer["id"],
        "branch_id": w.branch["id"],
        "invoice_date": today(),
        "lines": lines,
    }
    if freight is not None:
        body["freight_amount"] = freight
    made = must(w.api.post(SI, body), "bill create")
    return made


def approved(w: World, row: dict) -> dict:
    """Approve a bill and return it as saved."""
    must(w.api.post(f"{SI}/{row['id']}/approve", {}), "bill approve")
    return must(w.api.get(f"{SI}/{row['id']}"), "bill read")


def preview(w: World, keys: list[str]) -> dict:
    """Ask series-preview for these product keys."""
    query = "&".join(f"product_id={w.products[k]['id']}" for k in keys)
    return must(
        w.api.get(f"{SI}/series-preview?{query}&invoice_date={today()}"), "preview"
    )


def sequence(number: str) -> int:
    """Return the running number at the end of a bill number."""
    return int(re.findall(r"(\d+)$", number)[0])


def run_cases(w: World) -> None:
    """Drive design section 11."""
    api = w.api
    # 1. ONE_SERIES: an ASIAN-only bill still takes GENERAL.
    set_driver(api, "ONE_SERIES")
    shown = preview(w, ["A1"])
    # The preview names the series GENERAL; what GENERAL prints is the
    # sales-bill rule's own prefix (design section 4), read from the rule.
    general = f"{w.general}-"
    one = approved(w, bill(w, ["A1"]))
    record(
        "C01 ONE_SERIES takes GENERAL whatever the company holds",
        shown["reason"] == "ONE_SERIES"
        and shown["series_prefix"] == "GENERAL"
        and not one["invoice_number"].upper().startswith("ASIAN")
        and one["invoice_number"].startswith(general),
        f"preview {shown['series_prefix']}/{shown['reason']}, bill {one['invoice_number']}",
    )
    first_general = sequence(one["invoice_number"])

    set_driver(api, "BY_COMPANY")
    # 2. BY_COMPANY single company -> ASIAN, preview equals the saved number.
    shown = preview(w, ["A1"])
    asian_first = sequence(shown["number"])
    asian = [approved(w, bill(w, ["A1"]))]
    record(
        "C02 BY_COMPANY single-company bill takes the ASIAN series",
        asian[0]["invoice_number"].startswith("ASIAN-")
        and shown["reason"] == "ONE_COMPANY",
        f"bill {asian[0]['invoice_number']}",
    )
    record(
        "C03 series-preview text equals the saved number",
        shown["number"] == asian[0]["invoice_number"],
        f"preview {shown['number']}, saved {asian[0]['invoice_number']}",
    )
    # two products of the same company still ASIAN
    asian.append(approved(w, bill(w, ["A1", "A2"])))
    record(
        "C04 two products of one company take that company's series",
        asian[1]["invoice_number"].startswith("ASIAN-"),
        asian[1]["invoice_number"],
    )
    # 5. mixed -> GENERAL
    shown = preview(w, ["A1", "P1"])
    mixed = approved(w, bill(w, ["A1", "P1"]))
    record(
        "C05 a bill of two companies takes GENERAL",
        shown["reason"] == "MIXED"
        and mixed["invoice_number"].startswith(general)
        and shown["number"] == mixed["invoice_number"],
        f"preview {shown['reason']}, bill {mixed['invoice_number']}",
    )
    # 6. goods line with no company prefix -> GENERAL
    noco = approved(w, bill(w, ["N1"]))
    record(
        "C06 a goods line whose company has no prefix takes GENERAL",
        noco["invoice_number"].startswith(general),
        noco["invoice_number"],
    )
    mixed_noco = approved(w, bill(w, ["A1", "N1"]))
    record(
        "C07 one prefixed and one unprefixed company take GENERAL",
        mixed_noco["invoice_number"].startswith(general),
        mixed_noco["invoice_number"],
    )
    # 8. freight and a service line are ignored
    freight = approved(w, bill(w, ["A1"], freight="50", service=True))
    asian.append(freight)
    record(
        "C08 freight and a service line do not change the series",
        freight["invoice_number"].startswith("ASIAN-"),
        freight["invoice_number"],
    )
    # 9. PIDI has its own counter starting at 1
    pidi_first = sequence(preview(w, ["P1"])["number"])
    pidi = approved(w, bill(w, ["P1"]))
    record(
        "C09 a second company has a counter of its own",
        pidi["invoice_number"].startswith("PIDI-")
        and sequence(pidi["invoice_number"]) == pidi_first,
        pidi["invoice_number"],
    )
    # 10. gapless and unique per prefix
    seqs = [sequence(b["invoice_number"]) for b in asian]
    record(
        "C10 ASIAN numbers are unique and gapless",
        seqs == list(range(seqs[0], seqs[0] + len(seqs))) and seqs[0] == asian_first,
        f"sequence {seqs}",
    )
    gens = [
        first_general,
        sequence(mixed["invoice_number"]),
        sequence(noco["invoice_number"]),
        sequence(mixed_noco["invoice_number"]),
    ]
    record(
        "C11 GENERAL numbers are unique and gapless across the setting",
        gens == list(range(gens[0], gens[0] + len(gens))),
        f"sequence {gens}",
    )
    # 12. switch off and on again
    set_driver(api, "ONE_SERIES")
    off = approved(w, bill(w, ["A1"]))
    set_driver(api, "BY_COMPANY")
    on = approved(w, bill(w, ["A1"]))
    record(
        "C12 switching off and on neither resets nor reuses a number",
        off["invoice_number"].startswith(general)
        and sequence(off["invoice_number"]) == gens[-1] + 1
        and on["invoice_number"].startswith("ASIAN-")
        and sequence(on["invoice_number"]) == seqs[-1] + 1,
        f"off {off['invoice_number']}, on {on['invoice_number']}",
    )
    # 13. prefix too long refused at save
    asian_row = w.principals["ASIAN"]
    refused = api.put(
        f"/api/v1/products/principals/{asian_row['id']}",
        {
            "code": "ASIAN",
            "name": asian_row["name"],
            "bill_series_prefix": "ASIANPAINT",
        },
    )
    kept = next(
        p
        for p in rows(api.get("/api/v1/products/principals"), "principals")
        if p["code"] == "ASIAN"
    )
    record(
        "C13 a prefix that cannot fit in 16 characters is refused at save",
        refused[0] in (400, 409, 422) and kept["bill_series_prefix"] == "ASIAN",
        f"{refused[0]}: {said(refused)}",
    )
    fits = api.put(
        f"/api/v1/products/principals/{asian_row['id']}",
        {"code": "ASIAN", "name": asian_row["name"], "bill_series_prefix": "ASIAN"},
    )
    record(
        "C14 the prefix that fits is accepted",
        fits[0] == 200,
        said(fits) if fits[0] != 200 else "",
    )
    odd = api.put(
        f"/api/v1/products/principals/{asian_row['id']}",
        {"code": "ASIAN", "name": asian_row["name"], "bill_series_prefix": "AS-IAN"},
    )
    record(
        "C15 a prefix with a symbol is refused",
        odd[0] in (400, 409, 422),
        f"{odd[0]}",
    )
    # 16. a sales return keeps its own series
    before = preview(w, ["A1"])
    source = approved(w, bill(w, ["A1"]))
    line = source["lines"][0]
    made = api.post(
        SR,
        {
            "customer_id": w.customer["id"],
            "branch_id": w.branch["id"],
            "warehouse_id": w.warehouse["id"],
            "return_date": today(),
            "source_documents": [
                {
                    "source_document_type": "SALES_INVOICE",
                    "source_document_id": source["id"],
                }
            ],
            "lines": [
                {
                    "source_document_type": "SALES_INVOICE",
                    "source_document_id": source["id"],
                    "source_document_line_id": line["id"],
                    "line_number": 1,
                    "current_return_quantity": "1",
                }
            ],
        },
    )
    after = preview(w, ["A1"])
    if made[0] in (200, 201):
        number = str(data(made).get("return_number"))
        record(
            "C16 a sales return keeps its own series and leaves the ASIAN counter alone",
            not number.upper().startswith("ASIAN")
            and sequence(after["number"]) == sequence(before["number"]) + 1,
            f"return {number}; ASIAN next was {before['number']}, then bill, now {after['number']}",
        )
    else:
        record(
            "C16 a sales return keeps its own series", False, f"{made[0]} {said(made)}"
        )


def main() -> None:
    """Build the firm, drive the cases and print the tally."""
    print(f"Bill series drive, {BASE}")
    email, password = read_admin()
    platform = sign_in(email, password)
    firm_id = build_firm(platform)
    api = firm_admin(platform, firm_id)
    world = World(api)
    run_cases(world)
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)} of {len(RESULTS)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
