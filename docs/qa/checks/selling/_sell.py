"""Helpers the selling checks share (not a check; run.py skips it).

Firm ``one`` is a finished Wholesale firm with its Firm admin and a Viewer;
firm ``two`` is a second such firm, used to prove another firm's bill is not
printable. Each check makes its own product, customers and bills under a fresh
tag and puts the firm's print template back as it found it.
"""

from __future__ import annotations

import base64
import json
import pathlib
import re
import sys
import zlib
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common import (  # noqa: E402,F401
    PASSWORD,
    Api,
    Check,
    all_rows,
    check_brand,
    client,
    data,
    fetch,
    message,
    save_state,
    sign_in,
    state,
    suffix,
)

SO = "/api/v1/sales-orders"
SI = "/api/v1/sales-invoices"
DN = "/api/v1/delivery-notes"
QT = "/api/v1/quotations"
SETTINGS = f"{SO}/workflow-settings"
PRINT_TEMPLATE = "/api/v1/document-framework/print-templates/SALES_INVOICE"
LIC = "/api/v1/trade-licences"
DEFAULT_COPIES = ("ORIGINAL FOR RECIPIENT", "DUPLICATE FOR TRANSPORTER", "TRIPLICATE FOR SUPPLIER")


def today() -> date:
    """Return the firm's business day (India), as the server judges it."""
    return (datetime.now(UTC) + timedelta(hours=5, minutes=30)).date()


def must(answer: tuple[int, Any], what: str) -> Any:  # noqa: ANN401
    """Return the data of a 2xx answer or stop saying what was refused."""
    status, body = answer
    if status not in (200, 201):
        raise SystemExit(f"PRECONDITION {what}: {status} {message(body)}")
    return data(body)


def rows_of(answer: tuple[int, Any]) -> list[Any]:
    """Return the list of a list answer, or stop."""
    got = must(answer, "list")
    return got if isinstance(got, list) else []


def by_code(api: Api, path: str, code: str) -> dict:
    """Return the row with this code from a list."""
    joiner = "&" if "?" in path else "?"
    for row in rows_of(api.get(f"{path}{joiner}search={code}&page_size=100")):
        if row.get("code") == code:
            return row
    raise SystemExit(f"PRECONDITION no {code} at {path}")


def admin(which: str = "admin") -> Api:
    """Return a signed-in account of the module's state."""
    return client(which, "selling")


def pdf_text(raw: bytes) -> str:
    """Return the strings shown by a reportlab PDF (flate and ASCII85 streams)."""
    out: list[str] = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", raw, re.S):
        chunk = m.group(1).strip()
        body = chunk
        try:
            if chunk.endswith(b"~>"):
                body = base64.a85decode(chunk[:-2])
            body = zlib.decompress(body)
        except Exception:  # noqa: BLE001
            continue
        for s in re.findall(rb"\(((?:\\.|[^\\)])*)\)", body):
            out.append(s.decode("latin-1").replace("\\(", "(").replace("\\)", ")"))
    return "\n".join(out)


def pages(raw: bytes) -> list[tuple[int, int]]:
    """Return the (width, height) in points of each page, in order."""
    found = []
    for m in re.finditer(rb"/MediaBox\s*\[\s*([\d.\- ]+?)\s*\]", raw):
        a, b, w, h = (float(x) for x in m.group(1).split()[:4])
        found.append((round(w - a), round(h - b)))
    return found


def kind(size: tuple[int, int]) -> str:
    """Name a page size: A4, HALF (A4 width, half the height) or OTHER."""
    w, h = size
    if abs(w - 595) <= 2 and abs(h - 842) <= 3:
        return "A4"
    if abs(w - 595) <= 2 and abs(h - 421) <= 3:
        return "HALF"
    return f"OTHER{w}x{h}"


def kinds(raw: bytes) -> list[str]:
    """Return the page kinds of a PDF."""
    return [kind(s) for s in pages(raw)]


@contextmanager
def template(api: Api, **wanted: object):  # noqa: ANN201
    """Run a block with the firm's bill template changed, then put it back."""
    held = must(api.get(PRINT_TEMPLATE), "print template")
    base = {
        k: v for k, v in held.items() if k not in ("id", "document_type", "is_customised")
    }
    if not held.get("is_customised") and not base.get("copy_labels"):
        # A firm that never saved prints three copies although the template
        # answers none (recorded as D-PRT-1); saving [] would cut it to one.
        base["copy_labels"] = list(DEFAULT_COPIES)
    must(api.put(PRINT_TEMPLATE, {**base, **wanted}), "template changed")
    try:
        yield
    finally:
        must(api.put(PRINT_TEMPLATE, base), "template put back")


@contextmanager
def settings(api: Api, **wanted: object):  # noqa: ANN201
    """Run a block with workflow settings changed, and put them back after."""
    held = must(api.get(SETTINGS), "workflow settings")
    write_keys = (
        "quotation_stage", "sales_order_stage", "delivery_note_stage",
        "default_branch_id", "default_warehouse_id", "promotion_mode",
        "max_line_discount_percent", "rate_includes_tax",
        "new_outlets_need_approval", "reservation_lapse_days",
        "sales_order_approval", "delivery_note_approval",
        "sales_invoice_approval", "round_bills_to_rupee", "salesman_required",
        "box_and_piece_entry",
    )
    base = {k: held[k] for k in write_keys if k in held}
    must(api.put(SETTINGS, {**base, **wanted}), "settings changed")
    try:
        yield held
    finally:
        must(api.put(SETTINGS, base), "settings put back")


def counter(api: Api, **extra: object):  # noqa: ANN201
    """Settings with the order and note stages off, so a bill is typed alone."""
    return settings(api, sales_order_stage=False, delivery_note_stage=False, **extra)


def printed(api: Api, invoice_id: str, query: str = "") -> bytes:
    """Return a bill's PDF bytes, or stop if it did not print."""
    status, raw = api.raw(f"{SI}/{invoice_id}/print{query}")
    if status != 200 or raw[:4] != b"%PDF":
        raise SystemExit(f"PRECONDITION print {status} {raw[:200]!r}")
    return raw


def refusal_of(raw: bytes) -> str:
    """Return the words of a JSON refusal that came back as bytes."""
    try:
        return message(json.loads(raw.decode("utf-8")))
    except ValueError:
        return raw[:200].decode("latin-1")


def post_raw(api: Api, path: str, body: Any) -> tuple[int, bytes]:  # noqa: ANN401
    """POST JSON and return the answer's bytes untouched (a PDF or a refusal)."""
    headers = {"Content-Type": "application/json"}
    if api.token:
        headers["Authorization"] = f"Bearer {api.token}"
    if api.firm_id:
        headers["X-Firm-ID"] = api.firm_id
    return fetch("POST", path, json.dumps(body).encode("utf-8"), headers)


class Scene:
    """One stocked item (18%), one customer, and helpers to make bills."""

    def __init__(self, api: Api, stock: str = "200", price: str = "100") -> None:
        """Make the item (with stock in MAIN) and the customer."""
        self.api = api
        self.tag = suffix(5)
        self.branch = by_code(api, "/api/v1/branches", "HO")
        self.warehouse = by_code(api, "/api/v1/warehouses", "MAIN")
        self.piece = next(
            u["id"]
            for u in rows_of(api.get("/api/v1/uom-framework/uoms?page_size=100"))
            if u["code"] == "PIECE"
        )
        self.product = self.new_product("P", price, stock, "GST_18_LOCAL")
        self.customer = self.new_customer()

    def new_product(self, code: str, price: str, stock: str, tax: str) -> dict:
        """Make a stocked item of this scene's tag."""
        api = self.api
        made = must(
            api.post(
                "/api/v1/products",
                {
                    "code": f"{code}{self.tag}",
                    "name": f"Sell check item {code} {self.tag}",
                    "brand_id": check_brand(api),
                    "product_type": "STOCK_ITEM",
                    "tax_profile_group_code": tax,
                    "selling_price": price,
                    "purchase_price": "60",
                    "base_uom_id": self.piece,
                    "inventory_uom_id": self.piece,
                    "sales_uom_id": self.piece,
                    "purchase_uom_id": self.piece,
                },
            ),
            "product",
        )
        if stock == "0":
            return made
        stocked = must(
            api.post(
                "/api/v1/inventory/opening-stock",
                {
                    "branch_id": self.branch["id"],
                    "warehouse_id": self.warehouse["id"],
                    "reference_number": f"OS-{code}{self.tag}",
                    "posting_date": today().isoformat(),
                    "lines": [
                        {"product_id": made["id"], "quantity": stock, "unit_cost": "60"}
                    ],
                },
            ),
            "opening stock",
        )
        must(
            api.post(f"/api/v1/inventory/opening-stock/{stocked['id']}/post", {}),
            "post opening stock",
        )
        return made

    def new_customer(self, **extra: object) -> dict:
        """Make a customer of this scene's tag."""
        n = suffix(4)
        return must(
            self.api.post(
                "/api/v1/customers",
                {
                    "code": f"SL{self.tag}{n}",
                    "name": f"Sell buyer {self.tag}{n}",
                    "customer_type": "BUSINESS",
                    "currency_code": "INR",
                    **extra,
                },
            ),
            "customer",
        )

    def set_paper(self, customer: dict, paper: str | None) -> None:
        """Set a customer's Bill paper (HALF, A4 or None for the firm's)."""
        must(
            self.api.put(
                f"/api/v1/customers/{customer['id']}",
                {
                    "code": customer["code"],
                    "name": customer["name"],
                    "customer_type": customer["customer_type"],
                    "currency_code": customer["currency_code"],
                    "bill_page_size": paper,
                },
            ),
            "customer paper",
        )

    def bill_body(
        self,
        qty: str = "1",
        customer: dict | None = None,
        lines: int = 1,
        **extra: object,
    ) -> dict:
        """Return a counter-bill body of ``lines`` lines of the item."""
        return {
            "customer_id": (customer or self.customer)["id"],
            "branch_id": self.branch["id"],
            "invoice_date": today().isoformat(),
            "lines": [
                {
                    "line_number": n,
                    "product_id": self.product["id"],
                    "current_invoice_quantity": qty,
                    "warehouse_id": self.warehouse["id"],
                }
                for n in range(1, lines + 1)
            ],
            **extra,
        }

    def bill(
        self,
        customer: dict | None = None,
        lines: int = 1,
        qty: str = "1",
        approve: bool = True,
        **extra: object,
    ) -> dict:
        """Type a counter bill (the caller holds ``counter``) and approve it."""
        made = must(
            self.api.post(SI, self.bill_body(qty, customer, lines, **extra)), "bill"
        )
        if approve:
            made = must(
                self.api.post(f"{SI}/{made['id']}/approve", {}), "bill approve"
            )
        return made

    def staged_bill(
        self,
        qty: str,
        price: str | None = None,
        product: dict | None = None,
        customer: dict | None = None,
        rate_includes_tax: bool = False,
    ) -> tuple[dict, dict]:
        """Carry one sale through order, note and bill; return (order, bill)."""
        api = self.api
        prod = product or self.product
        cust = customer or self.customer
        day = today().isoformat()
        line: dict = {"line_number": 1, "product_id": prod["id"], "quantity": qty}
        if price is not None:
            line["unit_price"] = price
        order = must(
            api.post(
                SO,
                {
                    "customer_id": cust["id"],
                    "order_date": day,
                    "branch_id": self.branch["id"],
                    "warehouse_id": self.warehouse["id"],
                    "lines": [line],
                    "rate_includes_tax": rate_includes_tax,
                },
            ),
            "order",
        )
        must(api.post(f"{SO}/{order['id']}/approve", {}), "order approve")
        oline = must(api.get(f"{SO}/{order['id']}"), "order read")["lines"][0]
        note = must(
            api.post(
                DN,
                {
                    "sales_order_id": order["id"],
                    "delivery_date": day,
                    "lines": [
                        {
                            "sales_order_line_id": oline["id"],
                            "line_number": 1,
                            "current_delivery_quantity": qty,
                        }
                    ],
                },
            ),
            "note",
        )
        must(api.post(f"{DN}/{note['id']}/approve", {}), "note approve")
        must(api.post(f"{DN}/{note['id']}/dispatch", {}), "note dispatch")
        nline = must(api.get(f"{DN}/{note['id']}"), "note read")["lines"][0]
        bill = must(
            api.post(
                SI,
                {
                    "customer_id": cust["id"],
                    "branch_id": self.branch["id"],
                    "invoice_date": day,
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
                            "source_document_line_id": nline["id"],
                            "line_number": 1,
                            "current_invoice_quantity": qty,
                        }
                    ],
                },
            ),
            "bill",
        )
        bill = must(api.post(f"{SI}/{bill['id']}/approve", {}), "bill approve")
        return order, bill


SR = "/api/v1/sales-returns"
CN = "/api/v1/credit-notes"
PF = "/api/v1/proforma-invoices"
SM = "/api/v1/salesmen"
CREDIT = "/api/v1/customers/credit-settings"
GST = "/api/v1/tax-framework/gst-compliance-settings"
INV = "/api/v1/inventory"


def D(value: object) -> Decimal:  # noqa: N802
    """Return a Decimal from whatever the server sent."""
    return Decimal(str(value if value is not None else 0))


def stock(api: Api, product_id: str) -> tuple[Decimal, Decimal]:
    """Return (on hand, reserved) of a product, summed over its rows."""
    rows = all_rows(api, f"{INV}?product_id={product_id}&include_deleted=false")
    return (
        sum((D(r["current_quantity"]) for r in rows), Decimal(0)),
        sum((D(r["reserved_quantity"]) for r in rows), Decimal(0)),
    )


def ledger(api: Api, product_id: str, **filters: str) -> list[dict]:
    """Return a product's stock-ledger rows, oldest first."""
    extra = "".join(f"&{k}={v}" for k, v in filters.items())
    return all_rows(
        api,
        f"{INV}/ledger?product_id={product_id}{extra}"
        "&sort_by=created_at&sort_direction=asc",
    )


def owed(api: Api, customer_id: str) -> Decimal:
    """Return the customer's outstanding balance."""
    got = must(api.get(f"/api/v1/customers/{customer_id}"), "customer")
    return D(got["current_outstanding"])


def journal(api: Api, reference: str) -> list[dict]:
    """Return the journal entries whose reference matches a document number."""
    status, body = api.get(
        f"/api/v1/finance/journal-entries?search={reference}&page_size=50"
    )
    rows = data(body) if status == 200 else []
    return [e for e in rows if reference in str(e.get("reference_number"))]


def new_order(
    sc: "Scene",
    qty: str = "2",
    customer: dict | None = None,
    product: dict | None = None,
    approve: bool = False,
    line: dict | None = None,
    **extra: object,
) -> dict:
    """Raise (and optionally approve) an order of the scene's item."""
    body = {
        "customer_id": (customer or sc.customer)["id"],
        "order_date": today().isoformat(),
        "branch_id": sc.branch["id"],
        "warehouse_id": sc.warehouse["id"],
        "lines": [
            {
                "line_number": 1,
                "product_id": (product or sc.product)["id"],
                "quantity": qty,
                **(line or {}),
            }
        ],
        **extra,
    }
    made = must(sc.api.post(SO, body), "order")
    if approve:
        made = must(sc.api.post(f"{SO}/{made['id']}/approve", {}), "order approve")
    return made


def new_note(
    sc: "Scene", order: dict, qty: str, dispatch: bool = False, **extra: object
) -> dict:
    """Raise (approve and dispatch, if asked) a delivery note for part of an order."""
    line = must(sc.api.get(f"{SO}/{order['id']}"), "order read")["lines"][0]
    made = must(
        sc.api.post(
            DN,
            {
                "sales_order_id": order["id"],
                "delivery_date": today().isoformat(),
                "lines": [
                    {
                        "sales_order_line_id": line["id"],
                        "line_number": 1,
                        "current_delivery_quantity": qty,
                    }
                ],
                **extra,
            },
        ),
        "note",
    )
    if dispatch:
        must(sc.api.post(f"{DN}/{made['id']}/approve", {}), "note approve")
        made = must(sc.api.post(f"{DN}/{made['id']}/dispatch", {}), "note dispatch")
    return made


def bill_note(
    sc: "Scene", note: dict, qty: str, approve: bool = True, customer: dict | None = None
) -> dict:
    """Bill part of a delivery note; approve the bill unless told not to."""
    line = must(sc.api.get(f"{DN}/{note['id']}"), "note read")["lines"][0]
    made = must(
        sc.api.post(
            SI,
            {
                "customer_id": (customer or sc.customer)["id"],
                "branch_id": sc.branch["id"],
                "invoice_date": today().isoformat(),
                "source_documents": [
                    {"source_document_type": "DELIVERY_NOTE", "source_document_id": note["id"]}
                ],
                "lines": [
                    {
                        "source_document_type": "DELIVERY_NOTE",
                        "source_document_id": note["id"],
                        "source_document_line_id": line["id"],
                        "line_number": 1,
                        "current_invoice_quantity": qty,
                    }
                ],
            },
        ),
        "bill",
    )
    if approve:
        made = must(sc.api.post(f"{SI}/{made['id']}/approve", {}), "bill approve")
    return made


def return_body(
    sc: "Scene", source: dict, qty: str, kind: str = "SALES_INVOICE", **extra: object
) -> dict:
    """Return a sales-return body against a bill or a delivery note, line 1."""
    path = SI if kind == "SALES_INVOICE" else DN
    line = must(sc.api.get(f"{path}/{source['id']}"), "source read")["lines"][0]
    return {
        "customer_id": sc.customer["id"],
        "branch_id": sc.branch["id"],
        "warehouse_id": sc.warehouse["id"],
        "return_date": today().isoformat(),
        "source_documents": [{"source_document_type": kind, "source_document_id": source["id"]}],
        "lines": [
            {
                "source_document_type": kind,
                "source_document_id": source["id"],
                "source_document_line_id": line["id"],
                "line_number": 1,
                "current_return_quantity": qty,
                "restock_quantity": qty,
            }
        ],
        **extra,
    }


def complete_return(api: Api, made: dict) -> tuple[int, Any]:
    """Approve and complete a draft return; return the last raw answer."""
    status, body = api.post(f"{SR}/{made['id']}/approve", {})
    if status != 200:
        return status, body
    return api.post(f"{SR}/{made['id']}/complete", {})


@contextmanager
def credit_policy(api: Api, **wanted: object):  # noqa: ANN201
    """Run a block with the firm's credit policy changed, then put it back."""
    held = must(api.get(CREDIT), "credit settings")
    keys = (
        "enforcement", "warn_at_percent", "block_at_percent", "cash_discount_days",
        "cash_discount_percent", "overdue_interest_rate", "interest_grace_days",
        "collector_records_receipt",
    )
    base = {k: held[k] for k in keys if k in held}
    must(api.put(CREDIT, {**base, **wanted}), "credit settings changed")
    try:
        yield held
    finally:
        must(api.put(CREDIT, base), "credit settings put back")


@contextmanager
def gst_policy(api: Api, **wanted: object):  # noqa: ANN201
    """Run a block with the GST document policy changed, then put it back."""
    held = must(api.get(GST), "gst settings")
    keys = (
        "einvoice_applicable_from", "thirty_day_rule_from", "dispatch_without_invoice",
        "route_sale_needs_invoice", "itc_claim_basis", "rule37_mode",
        "supplier_irn_check", "gstr2b_tolerance", "eway_bill_limit",
        "filing_frequency", "quarterly_from", "qrmp_payment_method", "rule42_mode",
    )
    base = {k: held[k] for k in keys if k in held}
    must(api.put(GST, {**base, **wanted}), "gst settings changed")
    try:
        yield held
    finally:
        must(api.put(GST, base), "gst settings put back")


def salesman(api: Api, tag: str) -> dict:
    """Add a salesman to the firm's list."""
    return must(api.post(SM, {"name": f"Sell check {tag}{suffix(3)}"}), "salesman")


def ensure_user(
    platform: Api, email: str, title: str, firm_id: str, role_code: str
) -> str:
    """Find or make a user in one firm holding one role; return the user id."""
    found = [
        r
        for r in rows_of(platform.get(f"/api/v1/users?search={email}&page_size=10"))
        if r.get("email") == email
    ]
    if found:
        user_id = found[0]["id"]
    else:
        user_id = must(
            platform.post(
                "/api/v1/users",
                {
                    "email": email,
                    "full_name": title,
                    "password": PASSWORD,
                    "is_active": True,
                    "force_password_change": False,
                },
            ),
            f"user {email}",
        )["id"]
        must(
            platform.put(
                f"/api/v1/users/{user_id}/firms",
                {
                    "assignments": [
                        {"firm_id": firm_id, "is_primary": True, "is_active": True}
                    ]
                },
            ),
            "membership",
        )
    inside = platform.inside(firm_id)
    roles = rows_of(inside.get(f"/api/v1/roles?search={role_code}&page_size=50"))
    role = next(r for r in roles if r["code"] == role_code)
    must(
        platform.put(
            f"/api/v1/users/{user_id}/firms/{firm_id}/roles", {"ids": [role["id"]]}
        ),
        f"role {role_code}",
    )
    return str(user_id)
