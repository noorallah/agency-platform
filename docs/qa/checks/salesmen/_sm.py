"""Helpers the salesmen checks share (not a check; run.py skips it).

Firm ``one`` is a finished Wholesale firm (books open, GST template, head
office) with its Firm admin, a Viewer and a Sales executive; firm ``two`` is a
second such firm, used only to prove another firm's salesman is refused.
Each check makes its own product, customer and salesmen under a fresh tag.
"""

from __future__ import annotations

import base64
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
    message,
    save_state,
    sign_in,
    state,
    suffix,
)

SO = "/api/v1/sales-orders"
SI = "/api/v1/sales-invoices"
QT = "/api/v1/quotations"
DN = "/api/v1/delivery-notes"
SR = "/api/v1/sales-returns"
SM = "/api/v1/salesmen"
SETTINGS = f"{SO}/workflow-settings"


def D(value: object) -> Decimal:  # noqa: N802
    """Return a Decimal from whatever the server sent."""
    return Decimal(str(value if value is not None else 0))


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
    return client(which, "salesmen")


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


class Scene:
    """One stocked item, one customer, and helpers to make documents."""

    def __init__(self, api: Api, stock: str = "200") -> None:
        """Make the item (with stock in MAIN) and the customer."""
        self.api = api
        self.tag = suffix(5)
        self.branch = by_code(api, "/api/v1/branches", "HO")
        self.warehouse = by_code(api, "/api/v1/warehouses", "MAIN")
        units = rows_of(api.get("/api/v1/uom-framework/uoms?page_size=100"))
        piece = next(u["id"] for u in units if u["code"] == "PIECE")
        self.product = must(
            api.post(
                "/api/v1/products",
                {
                    "code": f"SM{self.tag}",
                    "name": f"Salesman check item {self.tag}",
                    "brand_id": check_brand(api),
                    "product_type": "STOCK_ITEM",
                    "tax_profile_group_code": "GST_18_LOCAL",
                    "selling_price": "100",
                    "purchase_price": "60",
                    "base_uom_id": piece,
                    "inventory_uom_id": piece,
                    "sales_uom_id": piece,
                    "purchase_uom_id": piece,
                },
            ),
            "product",
        )
        self.customer = self.new_customer()
        if stock:
            made = must(
                api.post(
                    "/api/v1/inventory/opening-stock",
                    {
                        "branch_id": self.branch["id"],
                        "warehouse_id": self.warehouse["id"],
                        "reference_number": f"OS-{self.tag}",
                        "posting_date": today().isoformat(),
                        "lines": [
                            {
                                "product_id": self.product["id"],
                                "quantity": stock,
                                "unit_cost": "60",
                            }
                        ],
                    },
                ),
                "opening stock",
            )
            must(
                api.post(f"/api/v1/inventory/opening-stock/{made['id']}/post", {}),
                "opening stock post",
            )

    def new_customer(self, **extra: object) -> dict:
        """Make a customer of this scene's tag."""
        n = suffix(4)
        return must(
            self.api.post(
                "/api/v1/customers",
                {
                    "code": f"SC{self.tag}{n}",
                    "name": f"Salesman buyer {self.tag}{n}",
                    "customer_type": "BUSINESS",
                    "currency_code": "INR",
                    **extra,
                },
            ),
            "customer",
        )

    def salesman(self, name: str | None = None, **extra: object) -> dict:
        """Add a salesman to the firm's list."""
        return must(
            self.api.post(SM, {"name": name or f"Sm {self.tag}{suffix(3)}", **extra}),
            "salesman",
        )

    def order_body(
        self, qty: str = "2", customer: dict | None = None, **extra: object
    ) -> dict:
        """Return an order body for one line of the item."""
        return {
            "customer_id": (customer or self.customer)["id"],
            "order_date": today().isoformat(),
            "branch_id": self.branch["id"],
            "warehouse_id": self.warehouse["id"],
            "lines": [
                {"line_number": 1, "product_id": self.product["id"], "quantity": qty}
            ],
            **extra,
        }

    def bill_body(
        self, qty: str = "1", customer: dict | None = None, **extra: object
    ) -> dict:
        """Return a counter-bill body for one line of the item."""
        return {
            "customer_id": (customer or self.customer)["id"],
            "branch_id": self.branch["id"],
            "invoice_date": today().isoformat(),
            "lines": [
                {
                    "line_number": 1,
                    "product_id": self.product["id"],
                    "current_invoice_quantity": qty,
                    "warehouse_id": self.warehouse["id"],
                }
            ],
            **extra,
        }

    def quote_body(self, qty: str = "1", **extra: object) -> dict:
        """Return a quotation body."""
        return {
            "customer_id": self.customer["id"],
            "quotation_date": today().isoformat(),
            "valid_until": (today() + timedelta(days=15)).isoformat(),
            "branch_id": self.branch["id"],
            "warehouse_id": self.warehouse["id"],
            "lines": [
                {"line_number": 1, "product_id": self.product["id"], "quantity": qty}
            ],
            **extra,
        }


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


PRINT_TEMPLATE = "/api/v1/document-framework/print-templates/SALES_INVOICE"


@contextmanager
def template(api: Api, **wanted: object):  # noqa: ANN201
    """Run a block with the firm's bill template changed, then put it back."""
    held = must(api.get(PRINT_TEMPLATE), "print template")
    base = {
        k: v for k, v in held.items() if k not in ("id", "document_type", "is_customised")
    }
    must(api.put(PRINT_TEMPLATE, {**base, **wanted}), "template changed")
    try:
        yield
    finally:
        must(api.put(PRINT_TEMPLATE, base), "template put back")


def printed(api: Api, invoice_id: str, query: str = "") -> str:
    """Return the text of a bill's PDF, or stop if it did not print."""
    status, raw = api.raw(f"{SI}/{invoice_id}/print{query}")
    if status != 200 or raw[:4] != b"%PDF":
        raise SystemExit(f"PRECONDITION print {status} {raw[:200]!r}")
    return pdf_text(raw)


T = "/api/v1/sales-territories"


def make_route(api: Api, tag: str, salesmen: list[tuple[str, bool]]) -> dict:
    """Make region > territory > route, put salesmen on the route; return it."""
    levels = {
        lv["level_code"]: lv["id"]
        for lv in must(api.get(f"{T}/hierarchy-levels"), "levels")["levels"]
    }

    def node(code: str, level: str, parent: str | None = None, **extra: object) -> dict:
        return must(
            api.post(
                T,
                {
                    "code": f"{code}{tag}",
                    "name": f"{code} {tag}",
                    "hierarchy_level_id": levels[level],
                    "parent_id": parent,
                    **extra,
                },
            ),
            f"node {code}",
        )

    region = node("RG", "REGION")
    territory = node("TR", "TERRITORY", region["id"])
    kind = must(
        api.post(f"{T}/route-types", {"code": f"RT{tag}", "name": f"RT {tag}"}),
        "route type",
    )
    route = node(
        "RO",
        "ROUTE",
        territory["id"],
        route_profile={
            "route_type_id": kind["id"],
            "visit_frequency": "WEEKLY",
            "working_days": [1],
        },
    )
    if salesmen:
        must(
            api.put(
                f"{T}/{route['id']}/salesmen",
                {
                    "assignments": [
                        {"salesman_id": sid, "is_primary": primary}
                        for sid, primary in salesmen
                    ]
                },
            ),
            "route salesmen",
        )
    return route


def second_product(sc: "Scene", code: str, price: str = "100") -> dict:
    """Make another stocked item of the scene's firm (stock 200 in MAIN)."""
    units = rows_of(sc.api.get("/api/v1/uom-framework/uoms?page_size=100"))
    piece = next(u["id"] for u in units if u["code"] == "PIECE")
    made = must(
        sc.api.post(
            "/api/v1/products",
            {
                "code": f"{code}{sc.tag}",
                "name": f"Salesman check {code} {sc.tag}",
                "brand_id": check_brand(sc.api),
                "product_type": "STOCK_ITEM",
                "tax_profile_group_code": "GST_18_LOCAL",
                "selling_price": price,
                "purchase_price": "60",
                "base_uom_id": piece,
                "inventory_uom_id": piece,
                "sales_uom_id": piece,
                "purchase_uom_id": piece,
            },
        ),
        "second product",
    )
    stock = must(
        sc.api.post(
            "/api/v1/inventory/opening-stock",
            {
                "branch_id": sc.branch["id"],
                "warehouse_id": sc.warehouse["id"],
                "reference_number": f"OS2-{sc.tag}{code}",
                "posting_date": (today() - timedelta(days=90)).isoformat(),
                "lines": [{"product_id": made["id"], "quantity": "500", "unit_cost": "60"}],
            },
        ),
        "opening stock 2",
    )
    must(sc.api.post(f"/api/v1/inventory/opening-stock/{stock['id']}/post", {}), "post os2")
    return made


def sell(
    sc: "Scene",
    salesman_id: str | None,
    qty: str,
    price: str,
    on: date,
    product: dict | None = None,
    customer: dict | None = None,
    collect: bool = False,
) -> dict:
    """Carry one sale through order, note and bill, all dated ``on``.

    Returns the approved invoice; with ``collect`` the whole bill is paid by
    a cash receipt dated ``on`` and allocated to it.
    """
    api = sc.api
    prod = product or sc.product
    cust = customer or sc.customer
    day = on.isoformat()
    body: dict = {
        "customer_id": cust["id"],
        "order_date": day,
        "branch_id": sc.branch["id"],
        "warehouse_id": sc.warehouse["id"],
        "lines": [
            {
                "line_number": 1,
                "product_id": prod["id"],
                "quantity": qty,
                "unit_price": price,
                # A firm that already trades may hold live offers (the Offers pass left
                # a stacking BULK5 on T1016VSH1-S); an explicit 0 refuses them, so the
                # sale is worth exactly price x quantity as these checks assume.
                "discount_percent": "0",
            }
        ],
    }
    if salesman_id:
        body["salesman_id"] = salesman_id
    order = must(api.post(SO, body), "order")
    must(api.post(f"{SO}/{order['id']}/approve", {}), "order approve")
    line = must(api.get(f"{SO}/{order['id']}"), "order read")["lines"][0]
    note = must(
        api.post(
            DN,
            {
                "sales_order_id": order["id"],
                "delivery_date": day,
                "lines": [
                    {
                        "sales_order_line_id": line["id"],
                        "line_number": 1,
                        "current_delivery_quantity": qty,
                    }
                ],
            },
        ),
        "delivery note",
    )
    must(api.post(f"{DN}/{note['id']}/approve", {}), "note approve")
    must(api.post(f"{DN}/{note['id']}/dispatch", {}), "note dispatch")
    nline = must(api.get(f"{DN}/{note['id']}"), "note read")["lines"][0]
    invoice = must(
        api.post(
            SI,
            {
                "customer_id": cust["id"],
                "branch_id": sc.branch["id"],
                "invoice_date": day,
                "source_documents": [
                    {"source_document_type": "DELIVERY_NOTE", "source_document_id": note["id"]}
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
        "invoice",
    )
    invoice = must(api.post(f"{SI}/{invoice['id']}/approve", {}), "invoice approve")
    invoice["order_id"] = order["id"]
    invoice["note_id"] = note["id"]
    if collect:
        must(
            api.post(
                "/api/v1/receipts",
                {
                    "party_id": cust["id"],
                    "settlement_date": day,
                    "amount": str(invoice["grand_total"]),
                    "method": "CASH",
                    "allocations": [
                        {"invoice_id": invoice["id"], "amount": str(invoice["grand_total"])}
                    ],
                },
            ),
            "receipt",
        )
    return invoice


def user_id_of(email: str) -> str:
    """Return the id of a user by e-mail, through the platform admin."""
    platform = admin("platform")
    for row in rows_of(platform.get(f"/api/v1/users?search={email}&page_size=10")):
        if row.get("email") == email:
            return str(row["id"])
    raise SystemExit(f"PRECONDITION no user {email}")


def counter(api: Api, **extra: object):  # noqa: ANN201
    """Settings with the order and note stages off, so a bill is typed alone."""
    return settings(api, sales_order_stage=False, delivery_note_stage=False, **extra)


COMM = "/api/v1/commission"


def month_bounds(day: date) -> tuple[date, date]:
    """Return the first and last day of the month ``day`` is in."""
    first = day.replace(day=1)
    nxt = (first + timedelta(days=32)).replace(day=1)
    return first, nxt - timedelta(days=1)


def rule(api: Api, salesman_id: str, start: date, **extra: object) -> dict:
    """Add a commission rule for a salesman, in force from ``start``."""
    return must(
        api.post(
            f"{COMM}/rules",
            {"salesman_id": salesman_id, "effective_from": start.isoformat(), **extra},
        ),
        "commission rule",
    )


def report_row(api: Api, salesman_id: str, start: date, end: date) -> dict:
    """Return the Collected-view row of one salesman for a window."""
    body = must(
        api.get(
            f"{COMM}/report?from_date={start}&to_date={end}&salesman_id={salesman_id}"
        ),
        "commission report",
    )
    rows = body["rows"] if isinstance(body, dict) else body
    return rows[0] if rows else {}
