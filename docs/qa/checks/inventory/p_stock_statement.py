"""Probe: the stock statement reconciles (opening + in - out = closing) and agrees with the valuation and the ledger."""
from _inv import *
from _flow import *

c = Check("p_stock_statement")
w = World()
a, b2 = w.warehouse(), w.warehouse()
p = w.product()
receive(w, a["id"], p["id"], 10, "61.37")
sell_and_dispatch(w, a["id"], p["id"], 4)
base = {"branch_id": w.branch_id, "product_id": p["id"], "transaction_date": w.today}
w.admin.post(f"{INV}/write-offs", {**base, "warehouse_id": a["id"], "quantity": "1", "reason": "DAMAGE", "reference_number": f"W{w.tag}"})
w.admin.post(f"{INV}/transfers", {**base, "from_warehouse_id": a["id"], "to_warehouse_id": b2["id"], "quantity": "2", "reference_number": f"T{w.tag}"})
rows = all_rows(w.admin, f"{INV}/reports/stock-statement?from_date={w.today}&to_date={w.today}", size=100)
r = next(x for x in rows if x["product_code"] == p["code"])
c.eq(D(r["opening_quantity"]) + D(r["inward_quantity"]) - D(r["outward_quantity"]), D(r["closing_quantity"]), "quantities reconcile")
c.eq(D(r["opening_value"]) + D(r["inward_value"]) - D(r["outward_value"]), D(r["closing_value"]), "values reconcile")
c.eq((D(r["inward_quantity"]), D(r["outward_quantity"]), D(r["closing_quantity"])), (D(10), D(5), D(5)), "10 in, 5 out (4 sold + 1 written off), 5 left; a transfer is neither")
val = next(v for v in w.valuation() if v["product_code"] == p["code"] and v["row_type"] == "ITEM")
c.eq((D(r["closing_quantity"]), D(r["closing_value"])), (D(val["quantity"]), D(val["value"])), "the closing line = the valuation report")
tot = next(x for x in rows if x["row_type"] == "TOTAL")
items = [x for x in rows if x["row_type"] == "ITEM"]
c.eq(sum(D(x["closing_value"]) for x in items), D(tot["closing_value"]), "the total row is the sum of the items")
c.eq(sum(D(x["inward_quantity"]) for x in items), D(tot["inward_quantity"]), "the inward total is the sum of the items")
st, b = w.admin.get(f"{INV}/reports/stock-statement?from_date={w.today}&to_date=2026-01-01")
c.eq(st, 422, "a period that ends before it starts is a 422")
st, b = w.admin.get(f"{INV}/reports/stock-statement?from_date=2020-01-01&to_date={w.today}")
c.ok(st == 200, "a period of several years reads", (st, message(b)))
st, b = w.admin.get(f"{INV}/reports/stock-statement?to_date={w.today}")
c.eq(st, 422, "from_date is required")
c.done()
