"""TC-STOCK-017: incoming and outgoing on availability; projected = available + incoming - outgoing."""
from _inv import *
from _flow import *
import _flow

c = Check("tc_stock_017")
w = World()
wh = w.warehouse()
p = w.product()
w.vendor_id = _flow._vendor(w)
po = must(w.admin.post("/api/v1/purchases", {"branch_id": w.branch_id, "warehouse_id": wh["id"], "vendor_id": w.vendor_id,
                                              "purchase_date": w.today,
                                              "lines": [{"product_id": p["id"], "ordered_quantity": "10", "unit_price": "100"}]}), "po")
must(w.admin.post(f"/api/v1/purchases/{po['id']}/submit", {}), "submit")
must(w.admin.post(f"/api/v1/purchases/{po['id']}/approve", {}), "approve")


def mine(path: str, key: str) -> dict:
    """The summary row of the product or warehouse, or {} when it is not listed."""
    st, b = w.admin.get(f"{INV}/summary/{path}")
    return next((r for r in data(b) if r["scope_id"] == key), {})


def figs(row: dict) -> tuple:
    """(available, incoming, outgoing, projected)."""
    return tuple(D(row.get(k, 0)) for k in ("available_quantity", "incoming_quantity", "outgoing_quantity", "projected_quantity"))


row = mine("by-product", p["id"])
c.ok(bool(row), "a product with no stock row but an open order is listed")
c.eq(figs(row), (D(0), D(10), D(0), D(10)), "approved order for 10: incoming 10, projected 10")
po = must(w.admin.get(f"/api/v1/purchases/{po['id']}"), "po")
g = must(w.admin.post("/api/v1/goods-receipts", {"purchase_order_id": po["id"], "receipt_date": w.today, "lines": [
    {"purchase_order_line_id": po["lines"][0]["id"], "line_number": 1, "current_receipt_quantity": "4",
     "unit_price": "100", "warehouse_id": wh["id"]}]}), "grn")
must(w.admin.post(f"/api/v1/goods-receipts/{g['id']}/complete", {}), "complete")
c.eq(figs(mine("by-product", p["id"])), (D(4), D(6), D(0), D(10)), "after receiving 4: incoming 6 (order less receipts)")
c.eq(figs(mine("by-warehouse", wh["id"])), (D(4), D(6), D(0), D(10)), "the warehouse row says the same")
# a sales order for 3 (fully reserved) and one for 1 more
s1 = sell_and_dispatch(w, wh["id"], p["id"], 3, dispatch=False)
r = figs(mine("by-product", p["id"]))
c.eq(r[0] + r[1] - r[2], r[3], "projected = available + incoming - outgoing after an order")
s2 = sell_and_dispatch(w, wh["id"], p["id"], 1, dispatch=False)
r = figs(mine("by-product", p["id"]))
c.eq(r[0] + r[1] - r[2], r[3], "the identity holds after a second order")
d = w.admin.post(f"/api/v1/delivery-notes/{s1['note']['id']}/dispatch", {})
c.eq(d[0], 200, "first note dispatched")
r = figs(mine("by-product", p["id"]))
c.eq(r[0] + r[1] - r[2], r[3], "the identity holds after a dispatch")
c.eq(r[1], D(6), "incoming is still 6 (nothing more received)")
s3 = sell_and_dispatch(w, wh["id"], p["id"], 5, dispatch=False)
r = figs(mine("by-product", p["id"]))
c.eq(r[0] + r[1] - r[2], r[3], "the identity holds after an order that exceeds stock")
c.done()
