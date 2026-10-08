"""Probe: a reference number typed twice, or not typed at all, on stock writes."""
from _inv import *

c = Check("p_reference_numbers")
w = World()
a, b2 = w.warehouse(), w.warehouse()
p = w.product()
w.stock_in(a["id"], p["id"], 50)
base = {"branch_id": w.branch_id, "product_id": p["id"], "transaction_date": w.today, "warehouse_id": a["id"]}
tb = {"branch_id": w.branch_id, "product_id": p["id"], "transaction_date": w.today, "from_warehouse_id": a["id"], "to_warehouse_id": b2["id"]}
for _ in range(2):
    st, b = w.admin.post(f"{INV}/write-offs", {**base, "quantity": "1", "reason": "DAMAGE"})
    c.eq(st, 201, "a write-off with no reference number gets one: " + message(b))
st1, b1 = w.admin.post(f"{INV}/write-offs", {**base, "quantity": "1", "reason": "DAMAGE", "reference_number": f"DUP{w.tag}"})
st2, b2_ = w.admin.post(f"{INV}/write-offs", {**base, "quantity": "1", "reason": "DAMAGE", "reference_number": f"DUP{w.tag}"})
c.eq(st1, 201, "first write-off with a typed reference")
c.ok(st2 == 201 or "reference" in message(b2_).lower() and "journal" not in message(b2_).lower(),
     "a second write-off with the same reference either posts or says so in stock words (not 'A journal entry with reference ... already exists')", (st2, message(b2_)))
for _ in range(2):
    st, b = w.admin.post(f"{INV}/transfers", {**tb, "quantity": "1"})
    c.eq(st, 201, "a transfer with no reference number gets one: " + message(b))
for _ in range(2):
    st, b = w.admin.post(f"{INV}/adjustments", {**base, "quantity": "-1", "reason_code": "LOSS"})
    c.eq(st, 201, "an adjustment with no reference number gets one: " + message(b))
c.done()
