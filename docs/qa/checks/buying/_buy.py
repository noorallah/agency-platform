"""Helpers the buying checks share (not a check; run.py skips it).

Firm ``one`` is a finished Wholesale firm with its Firm admin, a Viewer and a
Purchase Executive; firm ``two`` is a second such firm. Each check makes its
own vendor, product and documents under a fresh tag.
"""

from __future__ import annotations

import pathlib
import sys
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

PO = "/api/v1/purchases"
GR = "/api/v1/goods-receipts"
PI = "/api/v1/purchase-invoices"
PR = "/api/v1/purchase-returns"
PAY = "/api/v1/payments"
DN = "/api/v1/debit-notes"
SETTINGS = f"{PO}/workflow-settings"
INV = "/api/v1/inventory"


def today() -> date:
    """Return the firm's business day (India), as the server judges it."""
    return (datetime.now(UTC) + timedelta(hours=5, minutes=30)).date()


def D(value: object) -> Decimal:  # noqa: N802
    """Return a Decimal from whatever the server sent."""
    return Decimal(str(value if value is not None else 0))


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
    return client(which, "buying")


def stock(api: Api, product_id: str) -> Decimal:
    """Return on hand of a product, summed over its rows."""
    rows = all_rows(api, f"{INV}?product_id={product_id}&include_deleted=false")
    return sum((D(r["current_quantity"]) for r in rows), Decimal(0))


def ledger(api: Api, product_id: str) -> list[dict]:
    """Return a product's stock-ledger rows, oldest first."""
    return all_rows(
        api,
        f"{INV}/ledger?product_id={product_id}&sort_by=created_at&sort_direction=asc",
    )


def journal(api: Api, reference: str) -> list[dict]:
    """Return the journal entries whose reference matches a document number."""
    status, body = api.get(
        f"/api/v1/finance/journal-entries?search={reference}&page_size=50"
    )
    rows = data(body) if status == 200 else []
    return [e for e in rows if reference in str(e.get("reference_number"))]


def entry_net(api: Api, entry: dict) -> dict[str, Decimal]:
    """Net debit (+) / credit (-) per control purpose (or account id) of an entry."""
    accounts = {
        r["ledger_account_id"]: r["purpose"]
        for r in rows_of(api.get("/api/v1/finance/control-accounts"))
        if r.get("ledger_account_id")
    }
    net: dict[str, Decimal] = {}
    for line in entry["lines"]:
        key = accounts.get(line["ledger_account_id"], line["ledger_account_id"][:8])
        net[key] = (
            net.get(key, Decimal(0)) + D(line["debit_amount"]) - D(line["credit_amount"])
        )
    return net


def owing(api: Api, vendor_id: str, invoice_id: str) -> Decimal:
    """Return what a bill still owes, from the payment screen's outstanding list."""
    for row in rows_of(api.get(f"{PAY}/outstanding?vendor_id={vendor_id}")):
        if row.get("invoice_id") == invoice_id:
            return D(row["outstanding_amount"])
    return Decimal(0)


@contextmanager
def settings(api: Api, **wanted: object):  # noqa: ANN201
    """Run a block with the buying workflow settings changed, then put them back."""
    held = must(api.get(SETTINGS), "workflow settings")
    keys = (
        "purchase_order_stage", "goods_receipt_stage", "default_branch_id",
        "default_warehouse_id", "bill_price_tolerance_percent",
        "bill_tolerance_amount", "budget_policy", "order_quantity_policy",
        "purchase_order_approval", "goods_receipt_approval",
        "purchase_invoice_approval", "box_and_piece_entry",
    )
    base = {k: held[k] for k in keys if k in held}
    must(api.put(SETTINGS, {**base, **wanted}), "settings changed")
    try:
        yield held
    finally:
        must(api.put(SETTINGS, base), "settings put back")


class Scene:
    """One bought item (18% GST), one vendor, and helpers for the buying chain."""

    def __init__(self, api: Api) -> None:
        """Make the vendor and the item, with nothing on hand."""
        self.api = api
        self.tag = suffix(5)
        self.branch = by_code(api, "/api/v1/branches", "HO")
        self.warehouse = by_code(api, "/api/v1/warehouses", "MAIN")
        self.piece = next(
            u["id"]
            for u in rows_of(api.get("/api/v1/uom-framework/uoms?page_size=100"))
            if u["code"] == "PIECE"
        )
        self.vendor = self.new_vendor()
        self.product = self.new_product("B")

    def new_vendor(self, **extra: object) -> dict:
        """Make a vendor of this scene's tag."""
        n = suffix(4)
        return must(
            self.api.post(
                "/api/v1/vendors",
                {
                    "code": f"BV{self.tag}{n}",
                    "name": f"Buy check vendor {self.tag}{n}",
                    **extra,
                },
            ),
            "vendor",
        )

    def new_product(self, code: str, price: str = "100", **extra: object) -> dict:
        """Make a bought item with nothing on hand."""
        return must(
            self.api.post(
                "/api/v1/products",
                {
                    "code": f"{code}{self.tag}{suffix(2)}",
                    "name": f"Buy check item {code} {self.tag}",
                    "brand_id": check_brand(self.api),
                    "product_type": "STOCK_ITEM",
                    "tax_profile_group_code": "GST_18_LOCAL",
                    "selling_price": "150",
                    "purchase_price": price,
                    "base_uom_id": self.piece,
                    "inventory_uom_id": self.piece,
                    "sales_uom_id": self.piece,
                    "purchase_uom_id": self.piece,
                    **extra,
                },
            ),
            "product",
        )

    def order_body(
        self,
        qty: str = "10",
        price: str = "100",
        free: str | None = None,
        vendor: dict | None = None,
        product: dict | None = None,
        **line: object,
    ) -> dict:
        """Return a purchase-order body of one line."""
        row: dict[str, Any] = {
            "product_id": (product or self.product)["id"],
            "ordered_quantity": qty,
            "unit_price": price,
            **line,
        }
        if free is not None:
            row["free_quantity"] = free
        return {
            "branch_id": self.branch["id"],
            "warehouse_id": self.warehouse["id"],
            "vendor_id": (vendor or self.vendor)["id"],
            "purchase_date": today().isoformat(),
            "lines": [row],
        }

    def order(self, approve: bool = True, **kw: Any) -> dict:  # noqa: ANN401
        """Raise a purchase order; submit and approve it unless told not to."""
        made = must(self.api.post(PO, self.order_body(**kw)), "order")
        if approve:
            must(self.api.post(f"{PO}/{made['id']}/submit", {}), "order submit")
            must(self.api.post(f"{PO}/{made['id']}/approve", {}), "order approve")
            made = self.reload(made)
        return made

    def reload(self, order: dict) -> dict:
        """Read an order again."""
        return must(self.api.get(f"{PO}/{order['id']}"), "order read")

    def receipt_body(
        self, order: dict, qty: str, free: str = "0", **line: object
    ) -> dict:
        """Return a goods-receipt body for the order's first line."""
        oline = order["lines"][0]
        return {
            "purchase_order_id": order["id"],
            "receipt_date": today().isoformat(),
            "lines": [
                {
                    "purchase_order_line_id": oline["id"],
                    "line_number": 1,
                    "current_receipt_quantity": qty,
                    "free_quantity": free,
                    "unit_price": str(oline.get("unit_price", "100")),
                    "warehouse_id": self.warehouse["id"],
                    **line,
                }
            ],
        }

    def receive(
        self,
        order: dict,
        qty: str,
        free: str = "0",
        complete: bool = True,
        **line: object,
    ) -> dict:
        """Receive part of an order; complete it unless told not to."""
        made = must(
            self.api.post(GR, self.receipt_body(order, qty, free, **line)), "receipt"
        )
        if complete:
            made = must(
                self.api.post(f"{GR}/{made['id']}/complete", {}), "receipt complete"
            )
        return made

    def bill_body(
        self, receipt: dict, qty: str | None = None, price: str | None = None
    ) -> dict:
        """Return a supplier-bill body off a receipt's first line."""
        rline = must(self.api.get(f"{GR}/{receipt['id']}"), "receipt read")["lines"][0]
        quantity = qty or str(rline["current_receipt_quantity"])
        line: dict[str, Any] = {
            "source_document_type": "GOODS_RECEIPT",
            "source_document_id": receipt["id"],
            "source_document_line_id": rline["id"],
            "line_number": 1,
            "current_invoice_quantity": quantity,
        }
        if price is not None:
            line["unit_price"] = price
        return {
            "vendor_id": self.vendor["id"],
            "branch_id": self.branch["id"],
            "invoice_date": today().isoformat(),
            "supplier_invoice_number": f"SUP-{self.tag}{suffix(4)}",
            "supplier_invoice_date": today().isoformat(),
            "source_documents": [
                {
                    "source_document_type": "GOODS_RECEIPT",
                    "source_document_id": receipt["id"],
                }
            ],
            "lines": [line],
        }

    def bill(
        self,
        receipt: dict,
        qty: str | None = None,
        price: str | None = None,
        approve: bool = True,
        approval: dict | None = None,
    ) -> dict:
        """Bill a receipt; approve the bill unless told not to."""
        made = must(self.api.post(PI, self.bill_body(receipt, qty, price)), "bill")
        if approve:
            must(self.api.post(f"{PI}/{made['id']}/approve", approval or {}), "bill approve")
            made = must(self.api.get(f"{PI}/{made['id']}"), "bill read")
        return made

    def return_body(
        self,
        source: dict,
        qty: str,
        kind: str = "GOODS_RECEIPT",
        free: str | None = None,
        **line: object,
    ) -> dict:
        """Return a purchase-return body off a receipt or a bill, line 1."""
        path = GR if kind == "GOODS_RECEIPT" else PI
        sline = must(self.api.get(f"{path}/{source['id']}"), "source read")["lines"][0]
        row: dict[str, Any] = {
            "source_document_type": kind,
            "source_document_id": source["id"],
            "source_document_line_id": sline["id"],
            "line_number": 1,
            "current_return_quantity": qty,
            **line,
        }
        if free is not None:
            row["free_quantity"] = free
        return {
            "vendor_id": self.vendor["id"],
            "branch_id": self.branch["id"],
            "warehouse_id": self.warehouse["id"],
            "return_date": today().isoformat(),
            "source_documents": [
                {"source_document_type": kind, "source_document_id": source["id"]}
            ],
            "lines": [row],
        }

    def ret(
        self,
        source: dict,
        qty: str,
        kind: str = "GOODS_RECEIPT",
        complete: bool = True,
        free: str | None = None,
        outcome: str | None = None,
        **line: object,
    ) -> dict:
        """Raise a return; approve and complete it unless told not to."""
        body = self.return_body(source, qty, kind, free, **line)
        if outcome:
            body["outcome"] = outcome
        made = must(self.api.post(PR, body), "return")
        if complete:
            must(self.api.post(f"{PR}/{made['id']}/approve", {}), "return approve")
            must(self.api.post(f"{PR}/{made['id']}/complete", {}), "return complete")
            made = must(self.api.get(f"{PR}/{made['id']}"), "return read")
        return made

    def pay(
        self, amount: str, invoice: dict | None, method: str = "BANK"
    ) -> tuple[int, Any]:
        """Record a payment to the vendor, against one bill when given."""
        return self.api.post(
            PAY,
            {
                "party_id": self.vendor["id"],
                "settlement_date": today().isoformat(),
                "amount": amount,
                "method": method,
                "allocations": (
                    [{"invoice_id": invoice["id"], "amount": amount}] if invoice else []
                ),
            },
        )

    def received_and_billed(self, qty: str = "10") -> tuple[dict, dict, dict]:
        """Order, receive in full and bill: return (order, receipt, bill)."""
        order = self.order(qty=qty)
        receipt = self.receive(order, qty)
        return order, receipt, self.bill(receipt)


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
    role = next(
        r for r in roles
        if r["code"] == role_code and r.get("firm_id") in (None, firm_id)
    )
    must(
        platform.put(
            f"/api/v1/users/{user_id}/firms/{firm_id}/roles", {"ids": [role["id"]]}
        ),
        f"role {role_code}",
    )
    return str(user_id)


def custom_approver() -> Api:
    """Return a user on a custom role holding PURCHASE_APPROVE but neither of the
    over-tolerance and over-budget rights (made once, kept in the module's state)."""
    held = state("buying")
    email = held["accounts"].get("approver", {}).get("email")
    if not email:
        platform = admin("platform")
        firm = admin("admin")
        firm_id = held["firm_id"]
        code = "buyappr"
        roles = rows_of(firm.get(f"/api/v1/roles?search={code}&page_size=50"))
        role = next((r for r in roles if r["code"] == code and r.get("firm_id")), None)
        if role is None:
            role = must(
                firm.post("/api/v1/roles", {"code": code, "name": "Buying check approver", "is_active": True}),
                "custom role",
            )
        wanted = {"PURCHASE_VIEW", "PURCHASE_APPROVE", "PURCHASE_CREATE", "PURCHASE_UPDATE", "PURCHASE_RECEIVE"}
        perms = rows_of(platform.get("/api/v1/permissions?search=PURCHASE&page_size=100"))
        ids = [p["id"] for p in perms if p["code"] in wanted]
        must(firm.put(f"/api/v1/roles/{role['id']}/permissions", {"ids": ids}), "role permissions")
        email = f"{held['suffix']}.buyappr@fixtures.local"
        ensure_user(platform, email, "Buying check approver", firm_id, code)
        accounts = held["accounts"]
        accounts["approver"] = {"email": email, "firm_id": firm_id}
        save_state({"accounts": accounts}, "buying")
    return client("approver", "buying")
