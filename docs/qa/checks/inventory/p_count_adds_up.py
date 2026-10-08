"""Probe: a posted count line adds up when stock moved while the sheet was open (D-STK-45).

50 on hand, the sheet drawn up, 10 written off, 49 counted: the posted line reads Expected 40,
Counted 49, Variance +9 and the warehouse holds 49."""
from _inv import *

c = Check("p_count_adds_up")
w = World()
a = w.warehouse("A")
p = w.product()
w.stock_in(a["id"], p["id"], 50)
cnt = must(w.admin.post(f"{INV}/counts", {"branch_id": w.branch_id, "warehouse_id": a["id"], "count_date": w.today}), "count")
line = next(l for l in cnt["lines"] if l["product_id"] == p["id"])
c.eq(D(line["expected_quantity"]), D(50), "the draft line expects what was held when the sheet was drawn up")
st, b = w.admin.post(f"{INV}/write-offs", {"branch_id": w.branch_id, "product_id": p["id"], "transaction_date": w.today,
                                           "warehouse_id": a["id"], "quantity": "10", "reason": "DAMAGE", "reference_number": f"W{w.tag}"})
c.ok(st in (200, 201), "ten written off while the sheet is open", (st, message(b)))
st, b = w.admin.put(f"{INV}/counts/{cnt['id']}", {"lines": [{"product_id": p["id"], "counted_quantity": "49"}]})
c.eq(st, 200, "counted 49")
st, b = w.admin.post(f"{INV}/counts/{cnt['id']}/post", {})
c.eq(st, 200, "posted")
done = next(l for l in data(b)["lines"] if l["product_id"] == p["id"])
c.eq(D(done["expected_quantity"]), D(40), "Expected is what was held at posting")
c.eq(D(done["variance_quantity"]), D(9), "Variance is +9")
c.eq(D(done["counted_quantity"]) - D(done["expected_quantity"]), D(done["variance_quantity"]), "Counted - Expected = Variance")
c.eq(w.qty(p["id"], a["id"]), D(49), "the warehouse holds what was counted")
c.done()
