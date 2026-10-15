"""Helpers the box-and-piece probes share (not a check; run.py skips it).

Reuses the lot-firm fixture (TEST03) and its accounts from ``.state/lots.json``, so run
``lots/setup.py`` first, then ``box_piece/setup.py``.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lots"))

from _lot import *  # noqa: E402,F401,F403
from _lot import Api, Ctx, by_code, client, must, rows_of  # noqa: E402,F401

SALES_SETTINGS = "/api/v1/sales-orders/workflow-settings"
BUY_SETTINGS = "/api/v1/purchases/workflow-settings"
PACK = 12


def bp_admin() -> Api:
    """Return the TEST03 firm administrator (the lots fixture)."""
    return client("admin", "lots")


def switches(api: Api, sales: bool, buying: bool) -> None:
    """Set the selling and buying box-and-piece switches, leaving the rest as read."""
    s = must(api.get(SALES_SETTINGS), "sales settings")
    must(api.put(SALES_SETTINGS, {k: s[k] for k in ("quotation_stage", "sales_order_stage",
                                                   "delivery_note_stage")} | {"box_and_piece_entry": sales}),
         "sales switch")
    b = must(api.get(BUY_SETTINGS), "buying settings")
    must(api.put(BUY_SETTINGS, {k: b[k] for k in ("purchase_order_stage", "goods_receipt_stage")}
                 | {"box_and_piece_entry": buying}), "buying switch")


def box_uom(api: Api) -> dict:
    """Return the BOX unit, made where the firm has none."""
    units = rows_of(api.get("/api/v1/uom-framework/uoms?page_size=200"))
    found = next((u for u in units if u["code"] == "BOX"), None)
    if found:
        return found
    raise SystemExit("PRECONDITION the firm has no BOX unit")


def pack_product(api: Api, c: Ctx, code: str = "BP-BOX12") -> dict:
    """Return the product sold and bought in BOX with 1 BOX = 12 PIECE, made on first use."""
    try:
        return by_code(api, "/api/v1/products", code)
    except SystemExit:
        pass
    box = box_uom(api)
    made = must(api.post("/api/v1/products", {
        "code": code, "name": "Box and piece item", "brand_id": check_brand(api),
        "product_type": "STOCK_ITEM", "tax_profile_group_code": "GST_18_LOCAL",
        "selling_price": "100", "purchase_price": "50", "base_uom_id": c.piece["id"],
        "inventory_uom_id": c.piece["id"], "sales_uom_id": box["id"],
        "purchase_uom_id": box["id"]}), "pack product")
    must(api.post("/api/v1/uom-framework/conversion-rules", {
        "product_id": made["id"], "from_uom_id": box["id"], "to_uom_id": c.piece["id"],
        "conversion_factor": str(PACK), "effective_from": "2026-04-01"}), "rule 1 BOX = 12 PIECE")
    return made


def so_body(c: Ctx, product: dict, quantity: str, **line: object) -> dict:
    """Return a one-line sales order body for the probes."""
    return {"customer_id": c.customer["id"], "order_date": today().isoformat(),
            "warehouse_id": c.warehouse["id"], "branch_id": c.branch["id"],
            "lines": [{"line_number": 1, "product_id": product["id"], "quantity": quantity,
                       "unit_price": "10", **line}]}


def boxed_sale(api: Api, c: Ctx, p: dict, quantity: str = "41") -> dict:
    """Receive stock, then order (boxes and pieces on), deliver, dispatch and bill it.

    Returns {"order", "note", "invoice"} read fresh; the order carries the header flag.
    """
    c.receive([{"product": p, "qty": 100, "rate": 5}])
    order = must(api.post("/api/v1/sales-orders", so_body(c, p, quantity, pack_size="12")
                          | {"box_and_piece_entry": True}), "order")
    must(api.post(f"/api/v1/sales-orders/{order['id']}/approve", {}), "approve order")
    full = must(api.get(f"/api/v1/sales-orders/{order['id']}"), "order read")
    note = must(api.post("/api/v1/delivery-notes", {
        "sales_order_id": order["id"], "delivery_date": today().isoformat(),
        "lines": [{"sales_order_line_id": full["lines"][0]["id"], "line_number": 1,
                   "current_delivery_quantity": quantity}]}), "delivery note")
    must(api.post(f"/api/v1/delivery-notes/{note['id']}/approve", {}), "approve note")
    must(c.dispatch(note["id"]), "dispatch")
    note = must(api.get(f"/api/v1/delivery-notes/{note['id']}"), "note read")
    return {"order": full, "note": note, "invoice": c.bill(note)}
