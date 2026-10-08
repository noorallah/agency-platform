"""Buying, selling and the books, only as far as stock needs them (not a check)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from _inv import D, World, data, must


def _vendor(w: World) -> str:
    """A supplier made for this check."""
    code = f"V{w.tag}"
    return must(w.admin.post("/api/v1/vendors", {"code": code, "name": f"Supp {code}"}), "vendor")["id"]


def _customer(w: World) -> str:
    """A customer made for this check."""
    code = f"C{w.tag}"
    return must(
        w.admin.post(
            "/api/v1/customers",
            {"code": code, "name": f"Cust {code}", "customer_type": "BUSINESS", "currency_code": "INR"},
        ),
        "customer",
    )["id"]


def receive(
    w: World,
    warehouse_id: str,
    product_id: str,
    qty: Any,
    price: Any = "60",
    *,
    batch: str | None = None,
    expiry: str | None = None,
    mfg: str | None = None,
    serials: list[str] | None = None,
    complete: bool = True,
    line_extra: dict[str, Any] | None = None,
    po_line_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Order, approve and receive ``qty`` of a product into a warehouse.

    Returns {"order", "create", "receipt", "status"}; ``status`` is the answer
    of the completion when ``complete`` is true.
    """
    if not hasattr(w, "vendor_id"):
        w.vendor_id = _vendor(w)
    po = must(
        w.admin.post(
            "/api/v1/purchases",
            {
                "branch_id": w.branch_id,
                "warehouse_id": warehouse_id,
                "vendor_id": w.vendor_id,
                "purchase_date": w.today,
                "lines": [
                    {
                        "product_id": product_id,
                        "ordered_quantity": str(qty),
                        "unit_price": str(price),
                        **(po_line_extra or {}),
                    }
                ],
            },
        ),
        "purchase order",
    )
    must(w.admin.post(f"/api/v1/purchases/{po['id']}/submit", {}), "submit po")
    must(w.admin.post(f"/api/v1/purchases/{po['id']}/approve", {}), "approve po")
    po = must(w.admin.get(f"/api/v1/purchases/{po['id']}"), "read po")
    line = po["lines"][0]
    gline: dict[str, Any] = {
        "purchase_order_line_id": line["id"],
        "line_number": 1,
        "current_receipt_quantity": str(qty),
        "unit_price": str(price),
        "warehouse_id": warehouse_id,
    }
    if batch:
        gline["batch_number"] = batch
    if expiry:
        gline["expiry_date"] = expiry
    if mfg:
        gline["manufacturing_date"] = mfg
    if serials:
        gline["serial_numbers"] = serials
    gline.update(line_extra or {})
    answer = w.admin.post(
        "/api/v1/goods-receipts",
        {"purchase_order_id": po["id"], "receipt_date": w.today, "lines": [gline]},
    )
    out: dict[str, Any] = {"order": po, "create": answer}
    if answer[0] not in (200, 201):
        return out
    receipt = data(answer[1])
    out["receipt"] = receipt
    if complete:
        out["status"] = w.admin.post(f"/api/v1/goods-receipts/{receipt['id']}/complete", {})
    return out


def sell_and_dispatch(
    w: World,
    warehouse_id: str,
    product_id: str,
    qty: Any,
    *,
    price: Any = "100",
    serial_ids: list[str] | None = None,
    batches: list[dict[str, Any]] | None = None,
    dispatch: bool = True,
) -> dict[str, Any]:
    """Order, approve, note, approve and dispatch ``qty``; return every answer."""
    if not hasattr(w, "customer_id"):
        w.customer_id = _customer(w)
    so = must(
        w.admin.post(
            "/api/v1/sales-orders",
            {
                "customer_id": w.customer_id,
                "branch_id": w.branch_id,
                "warehouse_id": warehouse_id,
                "order_date": w.today,
                "lines": [
                    {
                        "line_number": 1,
                        "product_id": product_id,
                        "quantity": str(qty),
                        "unit_price": str(price),
                        "warehouse_id": warehouse_id,
                    }
                ],
            },
        ),
        "sales order",
    )
    approved = w.admin.post(f"/api/v1/sales-orders/{so['id']}/approve", {})
    out: dict[str, Any] = {"order": so, "approve": approved}
    if approved[0] != 200:
        return out
    so = must(w.admin.get(f"/api/v1/sales-orders/{so['id']}"), "read so")
    out["order"] = so
    line = so["lines"][0]
    nline: dict[str, Any] = {
        "sales_order_line_id": line["id"],
        "line_number": 1,
        "current_delivery_quantity": str(qty),
        "warehouse_id": warehouse_id,
    }
    if serial_ids:
        nline["serial_ids"] = serial_ids
    if batches:
        nline["batches"] = batches
    made = w.admin.post(
        "/api/v1/delivery-notes",
        {"sales_order_id": so["id"], "delivery_date": w.today, "lines": [nline]},
    )
    out["note_create"] = made
    if made[0] not in (200, 201):
        return out
    note = data(made[1])
    out["note"] = note
    out["note_approve"] = w.admin.post(f"/api/v1/delivery-notes/{note['id']}/approve", {})
    if dispatch:
        out["dispatch"] = w.admin.post(f"/api/v1/delivery-notes/{note['id']}/dispatch", {})
    return out


def control_accounts(w: World) -> dict[str, str]:
    """Purpose -> ledger account id of the firm control accounts."""
    rows = must(w.admin.get("/api/v1/finance/control-accounts"), "control accounts")
    return {r["purpose"]: r["ledger_account_id"] for r in rows if r.get("ledger_account_id")}


def entries(w: World, search: str) -> list[dict[str, Any]]:
    """Journal entries found by a search word."""
    status, body = w.admin.get(f"/api/v1/finance/journal-entries?search={search}&page_size=50")
    return data(body) if status == 200 else []


def entries_of(w: World, source_id: str) -> list[dict[str, Any]]:
    """Journal entries a document raised, by its source id (newest pages first)."""
    status, body = w.admin.get("/api/v1/finance/journal-entries?page=1&page_size=100")
    pages = int((body.get("pagination") or {}).get("total_pages", 1)) if status == 200 else 0
    found: list[dict[str, Any]] = []
    for page in range(1, min(pages, 30) + 1):
        status, body = w.admin.get(f"/api/v1/finance/journal-entries?page={page}&page_size=100")
        if status != 200:
            break
        found += [e for e in data(body) if e.get("source_id") == source_id]
    return found


def by_purpose(w: World, entry: dict[str, Any]) -> dict[str, Decimal]:
    """Net debit (+) / credit (-) of an entry per control purpose."""
    inverse = {v: k for k, v in control_accounts(w).items()}
    net: dict[str, Decimal] = {}
    for line in entry["lines"]:
        key = inverse.get(line["ledger_account_id"], line["ledger_account_id"][:8])
        net[key] = net.get(key, Decimal(0)) + D(line["debit_amount"]) - D(line["credit_amount"])
    return net
