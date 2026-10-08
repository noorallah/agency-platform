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


def listed_or_outranked(product: dict, kind: str, quantity: Decimal, level: Decimal, label: str) -> None:
    """The row is listed as it stands, or the ten listed of its kind are all at least as bad (D-STK-55)."""
    if product["code"] in kinds:
        c.eq(kinds[product["code"]], (kind, quantity, level), label)
        return
    gaps = [abs(D(r["level"]) - D(r["quantity"])) for r in after["rows"] if r["kind"] == kind]
    c.ok(len(gaps) == 10 and min(gaps) >= abs(level - quantity), f"{label}: not listed, so the ten listed are all at least as bad",
         (len(gaps), [str(g) for g in gaps]))
    c.eq(gaps, sorted(gaps, reverse=True), f"{label}: the {kind} rows come worst first")


listed_or_outranked(lo, "LOW", D(3), D(5), "low row")
listed_or_outranked(out, "OUT", D(0), D(2), "out row")
listed_or_outranked(ov, "OVER_MAXIMUM", D(50), D(20), "over-maximum row")
for kind in ("LOW", "OUT", "OVER_MAXIMUM"):
    gaps = [abs(D(r["level"]) - D(r["quantity"])) for r in after["rows"] if r["kind"] == kind]
    c.eq(gaps, sorted(gaps, reverse=True), f"the {kind} rows listed come worst first")
# the worst of a kind heads its rows however many there are (D-STK-55): one short by more than any before it
import time

worst = w.product("WORST")
need = 100000 + int(time.time()) % 100000000
w.opening(wh["id"], [{"product_id": worst["id"], "quantity": "1", "unit_cost": "60", "reorder_level": str(need)}])
low_rows = [r for r in data(w.admin.get(f"{INV}/alerts")[1])["rows"] if r["kind"] == "LOW"]
c.eq(low_rows[0]["product_code"], worst["code"], "the item short by most is the first low row")
row = w.rows(worst["id"])[0]
st, b = w.admin.put(f"{INV}/{row['id']}", {"branch_id": w.branch_id, "warehouse_id": wh["id"], "product_id": worst["id"], "reorder_level": "0"})
c.eq(st, 200, "its level taken off again: " + message(b)[:100])
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
