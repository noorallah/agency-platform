"""TC-STOCK-019: stock alerts and turnover in the ageing."""
from _inv import *
from _flow import *

c = Check("tc_stock_019")
w = World()
wh = w.warehouse()
lo, out, ov, mv = w.product("LO"), w.product("OUT"), w.product("OV"), w.product("MV")
before = data(w.admin.get(f"{INV}/alerts")[1])
w.opening(wh["id"], [
    {"product_id": lo["id"], "quantity": "3", "unit_cost": "60", "reorder_level": "5"},
    {"product_id": out["id"], "quantity": "5", "unit_cost": "60", "reorder_level": "2"},
    {"product_id": ov["id"], "quantity": "50", "unit_cost": "60", "maximum_level": "20"},
    {"product_id": mv["id"], "quantity": "20", "unit_cost": "60"},
])
w.admin.post(f"{INV}/write-offs", {"branch_id": w.branch_id, "warehouse_id": wh["id"], "product_id": out["id"],
                                    "quantity": "5", "reason": "LOSS", "transaction_date": w.today, "reference_number": f"Z{w.tag}"})
after = data(w.admin.get(f"{INV}/alerts")[1])
for k in ("low", "out", "over_maximum"):
    c.eq(after[k] - before[k], 1, f"alerts {k} grew by one")
kinds = {r["product_code"]: (r["kind"], D(r["quantity"]), D(r["level"])) for r in after["rows"]}
c.eq(kinds.get(lo["code"]), ("LOW", D(3), D(5)), "low row")
c.eq(kinds.get(out["code"]), ("OUT", D(0), D(2)), "out row")
c.eq(kinds.get(ov["code"]), ("OVER_MAXIMUM", D(50), D(20)), "over-maximum row")
# nothing is stored: raising the stock above the reorder level clears the alert
w.admin.post(f"{INV}/adjustments", {"branch_id": w.branch_id, "warehouse_id": wh["id"], "product_id": lo["id"],
                                     "quantity": "10", "transaction_date": w.today, "reference_number": f"UP{w.tag}", "reason_code": "LOSS"})
again = data(w.admin.get(f"{INV}/alerts")[1])
c.eq(again["low"], before["low"], "the alert clears when the stock does")
# ageing: issued last year and turnover
s = sell_and_dispatch(w, wh["id"], mv["id"], 5)
c.eq(s["dispatch"][0], 200, "5 of MV dispatched")
st, b = w.admin.get(f"{INV}/reports/stock-ageing")
rows = {r["product_code"]: r for r in all_rows(w.admin, f"{INV}/reports/stock-ageing", size=100)}
r = rows.get(mv["code"])
c.ok(r is not None, "MV in the ageing")
if r:
    c.eq((D(r["quantity"]), D(r["issued_last_year"]), D(r["turnover"] or 0)), (D(15), D(5), D("0.33")), "issued 5 of 15 on hand: turnover 0.33")
nr = rows.get(ov["code"])
c.ok(nr is not None and nr["turnover"] is None, "nothing issued: turnover empty", nr and nr["turnover"])
c.done()
