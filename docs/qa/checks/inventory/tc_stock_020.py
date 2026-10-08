"""TC-STOCK-020: barcode labels, and the product selling status."""
from _inv import *
from _flow import *
import _flow

c = Check("tc_stock_020")
w = World()
wh = w.warehouse()
a, b2 = w.product("LA"), w.product("LB")
w.stock_in(wh["id"], a["id"], 10)
LB = "/api/v1/products/labels"
for layout in ("A4_65", "A4_24", "ROLL_50X25"):
    st, body = w.admin.post(LB, {"items": [{"product_id": a["id"], "copies": 2}, {"product_id": b2["id"], "copies": 1}],
                                  "layout": layout, "skip": 3 if layout != "ROLL_50X25" else 0, "show_price": True})
    ok = st == 200 and (isinstance(body, bytes) and body[:4] == b"%PDF")
    c.ok(ok, f"labels {layout} come back as a PDF", (st, str(body)[:120]))
# labels from a goods receipt
r = receive(w, wh["id"], b2["id"], 3)
st, body = w.admin.raw(f"/api/v1/goods-receipts/{r['receipt']['id']}/labels")
c.ok(st == 200 and body[:4] == b"%PDF", "receipt labels are a PDF", (st, str(body)[:120]))
# a cancelled receipt is refused
r2 = receive(w, wh["id"], b2["id"], 2, complete=False)
w.admin.post(f"/api/v1/goods-receipts/{r2['receipt']['id']}/cancel", {"reason": "test"})
st, body = w.admin.raw(f"/api/v1/goods-receipts/{r2['receipt']['id']}/labels")
c.ok(st in (409, 422), "labels for a cancelled receipt are refused", (st, str(body)[:160]))
# Discontinued: still sells, refused on a purchase order, not suggested to reorder
st, upd = w.update_product(a, status="DISCONTINUED")
c.eq(st, 200, "set Discontinued " + message(upd))
_flow._customer  # noqa: B018
s = sell_and_dispatch(w, wh["id"], a["id"], 1, dispatch=False)
c.eq(s.get("approve", (0,))[0], 200, "a Discontinued product still sells")
st, body = w.admin.post("/api/v1/purchases", {"branch_id": w.branch_id, "warehouse_id": wh["id"], "vendor_id": w.vendor_id,
                                              "purchase_date": w.today,
                                              "lines": [{"product_id": a["id"], "ordered_quantity": "1", "unit_price": "10"}]})
c.refused((st, body), 422, a["code"], "a Discontinued product is refused on a purchase order by name")
# Not for sale: refused on a sales order, still bought
n = w.product("NFS", not_for_sale=True)
if not hasattr(w, "customer_id"):
    w.customer_id = _flow._customer(w)
st, body = w.admin.post("/api/v1/sales-orders", {"customer_id": w.customer_id, "branch_id": w.branch_id, "warehouse_id": wh["id"],
                                                 "order_date": w.today, "lines": [{"line_number": 1, "product_id": n["id"], "quantity": "1", "unit_price": "10", "warehouse_id": wh["id"]}]})
c.refused((st, body), 422, "not for sale", "a not-for-sale product is refused on a sales order")
st, body = w.admin.post("/api/v1/purchases", {"branch_id": w.branch_id, "warehouse_id": wh["id"], "vendor_id": w.vendor_id,
                                              "purchase_date": w.today,
                                              "lines": [{"product_id": n["id"], "ordered_quantity": "1", "unit_price": "10"}]})
c.eq(st, 201, "but it can still be bought")
c.done()
