"""TC-STOCK-014: count plans, ABC classes and blind sheets."""
from datetime import date, timedelta

from _inv import *
from _flow import *

c = Check("tc_stock_014")
w = World()
wh = w.warehouse()
x, z = w.product("X"), w.product("Z")
# Dearer than every earlier run's heavy mover: the firm keeps them all, and
# equal movers share class A by product id, so a flat 60 stopped being the
# heaviest once enough runs had gone by (round 10).
cost = 60 + len(data(w.admin.get(f"{INV}/abc-classes")[1]))
w.stock_in(wh["id"], x["id"], 1500, cost)
w.stock_in(wh["id"], z["id"], 10, 60)
s = sell_and_dispatch(w, wh["id"], x["id"], 1000)
c.eq(s["dispatch"][0], 200, "1000 dispatched (the heaviest mover of the firm)")
st, b = w.admin.get(f"{INV}/abc-classes")
classes = data(b)
c.eq(classes.get(x["id"]), "A", "the heavy mover is class A")
c.eq(classes.get(z["id"], "C"), "C", "a product never dispatched is not listed, which means C")
st, b = w.admin.post(f"{INV}/count-plans", {"name": f"Plan {w.tag}", "branch_id": w.branch_id, "warehouse_id": wh["id"],
                                             "abc_class": "A", "frequency_days": 30, "blind": True})
c.eq(st, 201, "plan created")
plan = data(b)
st, b = w.admin.post(f"{INV}/count-plans/{plan['id']}/sheet", {})
c.ok(st in (200, 201), "sheet drawn", (st, message(b)))
sheet = data(b)
c.eq([l["product_id"] for l in sheet["lines"]], [x["id"]], "the sheet counts exactly the class-A product")
c.eq(sheet["is_blind"], True, "the sheet is blind")
c.ok(all(l["expected_quantity"] in (None, "") for l in sheet["lines"]), "a blind sheet hides the system quantity",
     [l["expected_quantity"] for l in sheet["lines"]])
st, b = w.admin.get(f"{INV}/counts/{sheet['id']}")
c.ok(all(l["expected_quantity"] in (None, "") for l in data(b)["lines"]), "a blind sheet re-read still hides it")
st, b = w.admin.put(f"{INV}/counts/{sheet['id']}", {"lines": [{"product_id": x["id"], "counted_quantity": "499"}]})
c.eq(st, 200, "counted 499 against 500")
st, b = w.admin.post(f"{INV}/counts/{sheet['id']}/post", {})
c.eq(st, 200, "posted")
done = data(b)
c.eq(done["status"], "POSTED", "POSTED")
c.eq(D(done["lines"][0]["expected_quantity"]), D(500), "after posting the expected quantity is shown")
c.eq(w.qty(x["id"]), D(499), "stock now 499")
st, b = w.admin.get(f"{INV}/count-plans")
mine = [p for p in data(b) if p["id"] == plan["id"]]
c.eq(len(mine), 1, "plan listed")
if mine:
    c.eq(mine[0]["last_counted_on"], w.today, "last counted today")
    c.eq(mine[0]["next_due_on"], (date.fromisoformat(w.today) + timedelta(days=30)).isoformat(), "next due 30 days after")
    c.eq(mine[0]["is_due"], False, "not due now")
c.done()
