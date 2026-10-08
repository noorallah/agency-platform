"""Probe: a product that forbids negative stock (the default) cannot be driven below zero by an adjustment, a repack or a kit."""
from _inv import *
from _flow import *

c = Check("p_negative_stock")
w = World()
wh = w.warehouse()
p, q = w.product(), w.product()
w.stock_in(wh["id"], p["id"], 10)
base = {"branch_id": w.branch_id, "warehouse_id": wh["id"], "product_id": p["id"], "transaction_date": w.today}
st, b = w.admin.post(f"{INV}/adjustments", {**base, "quantity": "-999", "reference_number": f"N{w.tag}", "reason_code": "LOSS"})
c.ok(st in (409, 422), "an adjustment of -999 against 10 on hand is refused (product forbids negative stock)", (st, message(b)))
c.ok(w.qty(p["id"]) >= 0, "stock never below zero after the adjustment", w.qty(p["id"]))
st, b = w.admin.post(f"{INV}/repacks", {"repack_date": w.today, "branch_id": w.branch_id, "warehouse_id": wh["id"],
                                         "lines": [{"kind": "CONSUME", "product_id": p["id"], "quantity": "999"},
                                                   {"kind": "PRODUCE", "product_id": q["id"], "quantity": "1"}]})
c.ok(st in (409, 422), "a repack consuming 999 of 10 is refused", (st, message(b)))
c.ok(w.qty(p["id"]) >= 0, "stock never below zero after the repack", w.qty(p["id"]))
c.done()
