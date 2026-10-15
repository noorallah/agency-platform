"""Probe: purchase order -> receipt carries the buying pack 12 and the header flag."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _bp import *  # noqa: F401,F403
c0 = Check("p_bp_06"); api = bp_admin(); c = Ctx(api); p = pack_product(api, c)
piece = c.piece["id"]
s, b = api.post("/api/v1/purchases", {
    "branch_id": c.branch["id"], "warehouse_id": c.warehouse["id"], "vendor_id": c.vendor["id"],
    "purchase_date": today().isoformat(), "box_and_piece_entry": True,
    "lines": [{"product_id": p["id"], "ordered_quantity": "41", "unit_price": "5", "pack_size": "12",
               "purchase_uom_id": piece, "inventory_uom_id": piece}]})
c0.eq(s, 201, f"the order is saved ({message(b)})")
if s == 201:
    po = data(b)
    must(api.post(f"/api/v1/purchases/{po['id']}/submit", {}), "submit")
    must(api.post(f"/api/v1/purchases/{po['id']}/approve", {}), "approve")
    full = must(api.get(f"/api/v1/purchases/{po['id']}"), "po read")
    c0.eq((D(full["lines"][0].get("pack_size")), full.get("box_and_piece_entry")), (D(12), True),
          "the order line holds pack 12 and the header flag")
    g = must(api.post("/api/v1/goods-receipts", {
        "purchase_order_id": po["id"], "receipt_date": today().isoformat(), "invoice_reference": f"R{suffix(8)}",
        "lines": [{"purchase_order_line_id": full["lines"][0]["id"], "line_number": 1,
                   "current_receipt_quantity": "41", "unit_price": "5", "warehouse_id": c.warehouse["id"]}]}),
        "receipt")
    got = must(api.get(f"/api/v1/goods-receipts/{g['id']}"), "receipt read")
    c0.eq((D(got["lines"][0].get("pack_size")), got.get("box_and_piece_entry")), (D(12), True),
          "the receipt line holds the buying pack 12 and the header flag")
c0.done()
