"""Helpers the costing-by-lot checks share (not a check; run.py skips it)."""

from __future__ import annotations

import pathlib
import sys
import time
from datetime import timedelta as timedelta
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

INV = "/api/v1/inventory"


def D(value: Any) -> Decimal:  # noqa: N802
    """Return a Decimal from whatever the server sent."""
    return Decimal(str(value if value is not None else 0))


def today() -> date:
    """Return the firm's business day (India), as the server judges it."""
    return (datetime.now(UTC) + timedelta(hours=5, minutes=30)).date()


def must(answer: tuple[int, Any], what: str) -> Any:
    """Return the data of a 2xx answer or stop saying what was refused."""
    status, body = answer
    if status not in (200, 201):
        raise SystemExit(f"PRECONDITION {what}: {status} {message(body)}")
    return data(body)


def rows_of(answer: tuple[int, Any]) -> list[Any]:
    """Return the list of a list answer, or stop."""
    status, body = answer
    if status != 200:
        raise SystemExit(f"PRECONDITION list: {status} {message(body)}")
    got = data(body)
    return got if isinstance(got, list) else []


def by_code(api: Api, path: str, code: str) -> dict:
    """Return the row with this code from a list."""
    joiner = "&" if "?" in path else "?"
    for row in rows_of(api.get(f"{path}{joiner}search={code}&page_size=100")):
        if row.get("code") == code:
            return row
    raise SystemExit(f"PRECONDITION no {code} at {path}")


# ---------------------------------------------------------------- users / firms


def ensure_user(platform: Api, email: str, title: str, firm_id: str, role_code: str) -> None:
    """Find or make a user in one firm holding one role."""
    found = [r for r in rows_of(platform.get(f"/api/v1/users?search={email}&page_size=10"))
             if r.get("email") == email]
    if found:
        user_id = found[0]["id"]
    else:
        user_id = must(platform.post("/api/v1/users", {
            "email": email, "full_name": title, "password": PASSWORD,
            "is_active": True, "force_password_change": False}), f"user {email}")["id"]
        must(platform.put(f"/api/v1/users/{user_id}/firms", {"assignments": [
            {"firm_id": firm_id, "is_primary": True, "is_active": True}]}), "membership")
    roles = rows_of(platform.get(f"/api/v1/roles?search={role_code}&page_size=50"))
    role = next(r for r in roles if r["code"] == role_code)
    must(platform.put(f"/api/v1/users/{user_id}/firms/{firm_id}/roles", {"ids": [role["id"]]}),
         f"role {role_code}")


def new_average_firm(platform: Api, tag: str) -> dict:
    """Create, provision and finish a firm of its own, still on Average.

    Returns ``{"code", "id", "admin_email"}``; the admin is a FIRM_ADMIN made
    for it. Takes a minute or two (the migrations run).
    """
    code = f"LT{tag}{suffix(5)}"
    created = must(platform.post("/api/v1/firms", {
        "name": f"Lot check firm {code}", "code": code, "country": "IN",
        "currency_code": "INR", "financial_year_start": "2026-04-01",
        "deployment_mode": "SCHEMA", "schema_name": f"lotchk_{code.lower()}",
        "notes": "Made by docs/qa/checks/lots. Test data only."}), "firm")
    firm_id = created["id"]
    must(platform.post(f"/api/v1/firms/{firm_id}/provision", {}), "provision")
    base = f"/api/v1/firms/{firm_id}"
    for step in ("open-books", "apply-tax-template", "create-default-branch"):
        must(platform.post(f"{base}/{step}", {}), step)
    profiles = rows_of(platform.get(f"/api/v1/business-framework/firms/{firm_id}/profiles"))
    wanted = next((p for p in profiles if p.get("code") == "WHOLESALE"), None)
    if wanted:
        platform.put(f"/api/v1/business-framework/firms/{firm_id}/profile-assignment",
                     {"business_profile_id": wanted["id"], "is_active": True})
    ready = must(platform.get(f"{base}/readiness"), "readiness")
    if not ready.get("can_post"):
        raise SystemExit(f"PRECONDITION firm {code} cannot post: {ready}")
    email = f"{code.lower()}.admin@fixtures.local"
    ensure_user(platform, email, f"Lot admin {code}", firm_id, "FIRM_ADMIN")
    return {"code": code, "id": firm_id, "admin_email": email}


# ---------------------------------------------------------------- masters


class Ctx:
    """The masters a check trades with, in one firm."""

    def __init__(self, api: Api) -> None:
        self.api = api
        self.tag = suffix(5)
        self.branch = by_code(api, "/api/v1/branches", "HO")
        self.warehouse = by_code(api, "/api/v1/warehouses", "MAIN")
        units = rows_of(api.get("/api/v1/uom-framework/uoms?page_size=100"))
        self.piece = next(u for u in units if u["code"] == "PIECE")
        self.vendor = must(api.post("/api/v1/vendors", {
            "code": f"V{self.tag}", "name": f"Lot supplier {self.tag}"}), "vendor")
        self.customer = must(api.post("/api/v1/customers", {
            "code": f"C{self.tag}", "name": f"Lot buyer {self.tag}",
            "customer_type": "BUSINESS", "currency_code": "INR"}), "customer")

    def product(self, name: str = "B", batch: bool = True, price: str = "100", **extra: Any) -> dict:
        """Make a product of this check; batch-tracked with expiry by default."""
        piece = self.piece["id"]
        return must(self.api.post("/api/v1/products", {
            "code": f"P{name}{self.tag}", "name": f"Lot item {name} {self.tag}",
            "brand_id": check_brand(self.api), "product_type": "STOCK_ITEM",
            "tax_profile_group_code": "GST_18_LOCAL", "selling_price": price,
            "purchase_price": "50", "base_uom_id": piece, "inventory_uom_id": piece,
            "sales_uom_id": piece, "purchase_uom_id": piece,
            "track_batch": batch, "track_expiry": batch, **extra}), f"product {name}")

    def second_warehouse(self) -> dict:
        """Make another warehouse for a transfer."""
        return must(self.api.post("/api/v1/warehouses", {
            "code": f"W{self.tag}", "name": f"Lot second {self.tag}",
            "branch_id": self.branch["id"]}), "warehouse")

    # ------------------------------------------------------------ buying

    def receive(self, lines: list[dict], complete: bool = True, days_ago: int = 0) -> dict:
        """Order, approve and receive lines; each is product/qty/rate + batch bits.

        A line may carry ``batch``, ``expiry`` (date), ``mrp``. Returns the
        receipt (completed unless ``complete`` is False).
        """
        api, piece = self.api, self.piece["id"]
        order = must(api.post("/api/v1/purchases", {
            "branch_id": self.branch["id"], "warehouse_id": self.warehouse["id"],
            "vendor_id": self.vendor["id"], "purchase_date": today().isoformat(),
            "lines": [{"product_id": ln["product"]["id"], "ordered_quantity": str(ln["qty"]),
                       "unit_price": str(ln["rate"]), "purchase_uom_id": piece,
                       "inventory_uom_id": piece} for ln in lines]}), "purchase order")
        must(api.post(f"/api/v1/purchases/{order['id']}/submit", {}), "submit")
        must(api.post(f"/api/v1/purchases/{order['id']}/approve", {}), "approve po")
        full = must(api.get(f"/api/v1/purchases/{order['id']}"), "po read")
        recv_lines = []
        for number, (ln, po_line) in enumerate(zip(lines, full["lines"], strict=True), 1):
            row: dict[str, Any] = {
                "purchase_order_line_id": po_line["id"], "line_number": number,
                "current_receipt_quantity": str(ln["qty"]), "unit_price": str(ln["rate"]),
                "warehouse_id": self.warehouse["id"]}
            if ln.get("batch"):
                row["batch_number"] = ln["batch"]
            if ln.get("expiry"):
                row["expiry_date"] = ln["expiry"].isoformat()
            if ln.get("mrp"):
                row["mrp"] = str(ln["mrp"])
            for key in ("ptr", "pts", "retail_margin_percent", "wholesale_margin_percent"):
                if ln.get(key) is not None:
                    row[key] = str(ln[key])
            recv_lines.append(row)
        receipt = must(api.post("/api/v1/goods-receipts", {
            "purchase_order_id": order["id"], "receipt_date": (today() - timedelta(days=days_ago)).isoformat(),
            "invoice_reference": f"R{suffix(8)}", "lines": recv_lines}), "goods receipt")
        if complete:
            receipt = must(api.post(f"/api/v1/goods-receipts/{receipt['id']}/complete", {}),
                           "complete receipt")
        return receipt

    # ------------------------------------------------------------ selling

    def note(self, lines: list[dict], price: str = "100", approve: bool = True) -> dict:
        """Order, approve and make a delivery note (not dispatched).

        Each line is product/qty and optional ``picks`` [(batch_id, qty)].
        Returns {"order", "note"} with the note approved when asked.
        """
        api = self.api
        order = must(api.post("/api/v1/sales-orders", {
            "customer_id": self.customer["id"], "order_date": today().isoformat(),
            "warehouse_id": self.warehouse["id"], "branch_id": self.branch["id"],
            "lines": [{"line_number": i, "product_id": ln["product"]["id"],
                       "quantity": str(ln["qty"]), "unit_price": price}
                      for i, ln in enumerate(lines, 1)]}), "sales order")
        must(api.post(f"/api/v1/sales-orders/{order['id']}/approve", {}), "approve so")
        full = must(api.get(f"/api/v1/sales-orders/{order['id']}"), "so read")
        dn_lines = []
        for i, (ln, so_line) in enumerate(zip(lines, full["lines"], strict=True), 1):
            row: dict[str, Any] = {"sales_order_line_id": so_line["id"], "line_number": i,
                                   "current_delivery_quantity": str(ln["qty"])}
            if ln.get("picks"):
                row["batches"] = [{"batch_id": b, "quantity": str(q)} for b, q in ln["picks"]]
            dn_lines.append(row)
        dn = must(api.post("/api/v1/delivery-notes", {
            "sales_order_id": order["id"], "delivery_date": today().isoformat(),
            "lines": dn_lines}), "delivery note")
        if approve:
            dn = must(api.post(f"/api/v1/delivery-notes/{dn['id']}/approve", {}), "approve dn")
        return {"order": order, "note": dn}

    def dispatch(self, note_id: str, confirm: bool = False) -> tuple[int, Any]:
        """Dispatch a delivery note; return the raw answer."""
        query = "?bill_without_stock=true" if confirm else ""
        return self.api.post(f"/api/v1/delivery-notes/{note_id}/dispatch{query}", {})

    def sell(self, lines: list[dict], price: str = "100") -> dict:
        """Order, deliver, dispatch (nothing confirmed) and return {"order","note"}."""
        made = self.note(lines, price)
        must(self.dispatch(made["note"]["id"]), "dispatch")
        made["note"] = must(self.api.get(f"/api/v1/delivery-notes/{made['note']['id']}"), "dn read")
        return made

    def bill(self, note: dict, quantities: list[str] | None = None, approve: bool = True) -> dict:
        """Raise (and approve) a sales bill off a dispatched note's lines."""
        api = self.api
        full = must(api.get(f"/api/v1/delivery-notes/{note['id']}"), "dn read")
        lines = []
        for i, nl in enumerate(full["lines"], 1):
            qty = quantities[i - 1] if quantities else str(nl["current_delivery_quantity"])
            lines.append({"source_document_type": "DELIVERY_NOTE", "source_document_id": note["id"],
                          "source_document_line_id": nl["id"], "line_number": i,
                          "current_invoice_quantity": qty})
        invoice = must(api.post("/api/v1/sales-invoices", {
            "customer_id": self.customer["id"], "branch_id": self.branch["id"],
            "invoice_date": today().isoformat(),
            "source_documents": [{"source_document_type": "DELIVERY_NOTE",
                                  "source_document_id": note["id"]}],
            "lines": lines}), "sales invoice")
        if approve:
            invoice = must(api.post(f"/api/v1/sales-invoices/{invoice['id']}/approve", {}),
                           "approve invoice")
        return must(api.get(f"/api/v1/sales-invoices/{invoice['id']}"), "invoice read")

    # ------------------------------------------------------------ reading

    def batches(self, product: dict) -> list[dict]:
        """Return the product's batch rows (one per lot), oldest first."""
        rows = all_rows(self.api, f"/api/v1/batch-serial/batches?product_id={product['id']}"
                                  "&sort_by=created_at&sort_direction=asc")
        return [r for r in rows if r.get("product_id") == product["id"]]

    def lots(self, product: dict, api: Api | None = None) -> list[dict]:
        """Return the product's lot valuation rows."""
        answer = (api or self.api).get(f"{INV}/reports/stock-valuation/lots?product_id={product['id']}")
        return rows_of(answer)

    def stock(self, product: dict) -> Decimal:
        """Return the product's on-hand total across the lot report."""
        return sum((D(r["quantity"]) for r in self.lots(product)), Decimal(0))

    def adjust(self, product: dict, qty: str, **extra: Any) -> tuple[int, Any]:
        """Post a stock adjustment in MAIN."""
        body = {"branch_id": self.branch["id"], "warehouse_id": self.warehouse["id"],
                "product_id": product["id"], "quantity": qty,
                "transaction_date": today().isoformat(), **extra}
        return self.api.post(f"{INV}/adjustments", body)

    def write_off(self, product: dict, qty: str, **extra: Any) -> tuple[int, Any]:
        """Write stock off in MAIN."""
        body = {"branch_id": self.branch["id"], "warehouse_id": self.warehouse["id"],
                "product_id": product["id"], "quantity": qty, "reason": "DAMAGE",
                "transaction_date": today().isoformat(), **extra}
        return self.api.post(f"{INV}/write-offs", body)

    def transfer(self, product: dict, qty: str, to_warehouse: dict, **extra: Any) -> tuple[int, Any]:
        """Transfer stock from MAIN to another warehouse."""
        body = {"branch_id": self.branch["id"], "from_warehouse_id": self.warehouse["id"],
                "to_warehouse_id": to_warehouse["id"], "product_id": product["id"],
                "quantity": qty, "transaction_date": today().isoformat(), **extra}
        return self.api.post(f"{INV}/transfers", body)


def lot_admin() -> Api:
    """Return the TEST03 firm administrator."""
    return client("admin", "lots")


def pause() -> None:
    """Breathe between heavy calls."""
    time.sleep(0.05)


def lotmap(c: Ctx, product: dict, api: Api | None = None) -> dict[str, dict]:
    """Return the product's lot rows keyed by printed batch ('' for none, then ref)."""
    out: dict[str, dict] = {}
    for row in c.lots(product, api):
        out[row["batch_number"] or row["lot_reference"]] = row
    return out


def batch_of(c: Ctx, product: dict, number: str) -> dict:
    """Return the product's batch row with this batch number."""
    for row in c.batches(product):
        if row["batch_number"] == number:
            return row
    raise SystemExit(f"PRECONDITION no batch {number} for {product['code']}")


def two_lots(c: Ctx, product: dict, qa: int = 10, qb: int = 10,
             ra: int = 40, rb: int = 42) -> dict:
    """Receive LOTA (expires first, +180 days) and LOTB (+365 days) on one receipt."""
    receipt = c.receive([
        {"product": product, "qty": qa, "rate": ra, "batch": "LOTA",
         "expiry": today() + timedelta(days=180), "mrp": 150},
        {"product": product, "qty": qb, "rate": rb, "batch": "LOTB",
         "expiry": today() + timedelta(days=365), "mrp": 150}])
    return {"receipt": receipt, "a": batch_of(c, product, "LOTA"),
            "b": batch_of(c, product, "LOTB")}


def trail(api: Api, batch_id: str) -> tuple[int, Any]:
    """Read a lot's trail."""
    return api.get(f"/api/v1/batch-serial/batches/{batch_id}/trail")


def sales_return(c: Ctx, invoice: dict, quantity: str, batch_number: str | None = None) -> tuple[int, Any]:
    """Raise (draft) a sales return of the invoice's first line; return the raw answer."""
    line = invoice["lines"][0]
    row: dict[str, Any] = {
        "source_document_type": "SALES_INVOICE", "source_document_id": invoice["id"],
        "source_document_line_id": line["id"], "line_number": 1,
        "current_return_quantity": quantity}
    if batch_number:
        row["batch_number"] = batch_number
    return c.api.post("/api/v1/sales-returns", {
        "customer_id": c.customer["id"], "branch_id": c.branch["id"],
        "warehouse_id": c.warehouse["id"], "return_date": today().isoformat(),
        "source_documents": [{"source_document_type": "SALES_INVOICE",
                              "source_document_id": invoice["id"]}],
        "lines": [row]})


def complete_return(c: Ctx, made: dict) -> tuple[int, Any]:
    """Approve and complete a draft sales return; return the last raw answer."""
    s, b = c.api.post(f"/api/v1/sales-returns/{made['id']}/approve", {})
    if s != 200:
        return s, b
    return c.api.post(f"/api/v1/sales-returns/{made['id']}/complete", {})


def purchase_return(c: Ctx, receipt: dict, quantity: str, complete: bool = True) -> tuple[int, Any]:
    """Raise (and complete) a purchase return of the receipt's first line; raw answer."""
    full = must(c.api.get(f"/api/v1/goods-receipts/{receipt['id']}"), "receipt")
    line = full["lines"][0]
    s, b = c.api.post("/api/v1/purchase-returns", {
        "vendor_id": c.vendor["id"], "branch_id": c.branch["id"], "warehouse_id": c.warehouse["id"],
        "return_date": today().isoformat(),
        "source_documents": [{"source_document_type": "GOODS_RECEIPT", "source_document_id": receipt["id"]}],
        "lines": [{"source_document_type": "GOODS_RECEIPT", "source_document_id": receipt["id"],
                   "source_document_line_id": line["id"], "line_number": 1,
                   "current_return_quantity": quantity}]})
    if s != 201 or not complete:
        return s, b
    ret = data(b)
    s, b = c.api.post(f"/api/v1/purchase-returns/{ret['id']}/approve", {})
    if s == 200:
        s, b = c.api.post(f"/api/v1/purchase-returns/{ret['id']}/complete", {})
    if s != 200:
        c.api.post(f"/api/v1/purchase-returns/{ret['id']}/cancel", {"reason": "check clean-up"})
    return s, b


def lot_settings(api: Api, allow: bool) -> None:
    """Set the firm's billing-without-stock switch (a by-lot firm)."""
    must(api.put(f"{INV}/lot-settings", {"allow_billing_without_stock": allow}), "lot settings")


def supplier_bill(c: Ctx, receipt: dict, quantity: str, rate: str, approve: bool = True) -> tuple[int, Any]:
    """Raise (and approve) a supplier bill off the receipt's first line; raw answer."""
    full = must(c.api.get(f"/api/v1/goods-receipts/{receipt['id']}"), "receipt")
    line = full["lines"][0]
    s, b = c.api.post("/api/v1/purchase-invoices", {
        "vendor_id": c.vendor["id"], "branch_id": c.branch["id"],
        "invoice_date": today().isoformat(), "supplier_invoice_number": f"SB{suffix(8)}",
        "supplier_invoice_date": today().isoformat(),
        "source_documents": [{"source_document_type": "GOODS_RECEIPT", "source_document_id": receipt["id"]}],
        "lines": [{"source_document_type": "GOODS_RECEIPT", "source_document_id": receipt["id"],
                   "source_document_line_id": line["id"], "line_number": 1,
                   "current_invoice_quantity": quantity, "unit_price": rate}]})
    if s != 201 or not approve:
        return s, b
    bill = data(b)
    return c.api.post(f"/api/v1/purchase-invoices/{bill['id']}/approve", {})


def journal_lines(api: Api, needle: str) -> list[dict]:
    """Return journal entries found by a search word, each with its lines read in full."""
    out = []
    for entry in rows_of(api.get(f"/api/v1/finance/journal-entries?search={needle}&page_size=20")):
        full = must(api.get(f"/api/v1/finance/journal-entries/{entry['id']}"), "journal")
        out.append(full)
    return out


def firm_admin(info: dict) -> Api:
    """Sign in as the FIRM_ADMIN of a firm made by new_average_firm."""
    return sign_in(info["admin_email"], PASSWORD, info["id"])


def opening_stock(c: Ctx, product: dict, quantity: str, cost: str) -> None:
    """Put units of a product in MAIN through a posted opening stock."""
    made = must(c.api.post(f"{INV}/opening-stock", {
        "branch_id": c.branch["id"], "warehouse_id": c.warehouse["id"],
        "reference_number": f"OS-{suffix(8)}", "posting_date": today().isoformat(),
        "lines": [{"product_id": product["id"], "quantity": quantity, "unit_cost": cost}]}), "opening stock")
    must(c.api.post(f"{INV}/opening-stock/{made['id']}/post", {}), "opening stock post")


def margin_product(api: Api) -> dict:
    """Return the fixture's LOT-MARGIN product (retail 25, wholesale 12.5)."""
    return by_code(api, "/api/v1/products", "LOT-MARGIN")


def receipt_line(api: Api, receipt: dict) -> dict:
    """Return the first line of a receipt, read fresh."""
    return must(api.get(f"/api/v1/goods-receipts/{receipt['id']}"), "receipt read")["lines"][0]


def lot_of_receipt(api: Api, product: dict, line: dict) -> dict:
    """Return the batch row a receipt line made (newest batch of the product)."""
    rows = all_rows(api, f"/api/v1/batch-serial/batches?product_id={product['id']}"
                         "&sort_by=created_at&sort_direction=desc", 10)
    return next(r for r in rows if r["product_id"] == product["id"])
