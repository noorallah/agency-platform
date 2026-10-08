"""TC-STOCK-002: a transfer between warehouses posts no journal; over-transfer refused."""
from _inv import *
from _flow import *

c = Check("tc_stock_002")
w = World()
w1, w2 = w.warehouse("A"), w.warehouse("B")
p = w.product()
w.stock_in(w1["id"], p["id"], 50)
ref = f"TRF-{w.tag}"
body = {
    "branch_id": w.branch_id, "from_warehouse_id": w1["id"], "to_warehouse_id": w2["id"],
    "product_id": p["id"], "quantity": "3", "reference_number": ref, "transaction_date": w.today,
}
before = len(entries(w, ref))
st, b = w.admin.post(f"{INV}/transfers", body)
c.eq(st, 201 if st == 201 else 200, "transfer accepted")
c.eq((w.qty(p["id"], w1["id"]), w.qty(p["id"], w2["id"]), w.qty(p["id"])),
     (D(47), D(3), D(50)), "47 / 3 / total 50")
led = w.ledger(p["id"])
types = {(x["transaction_type"], x["warehouse_id"], D(x["quantity"]), x["reference_number"]) for x in led}
c.ok(("TRANSFER_OUT", w1["id"], D(3), ref) in types, "TRANSFER_OUT 3 at source", sorted(types))
c.ok(("TRANSFER_IN", w2["id"], D(3), ref) in types, "TRANSFER_IN 3 at destination", sorted(types))
c.eq(len(entries(w, ref)), before, "no journal for a plain transfer")
st, b = w.admin.post(f"{INV}/transfers", {**body, "quantity": "999", "reference_number": ref + "X"})
c.refused((st, b), 422 if st == 422 else 409, "available", "999 refused naming availability")
c.eq(w.qty(p["id"], w1["id"]), D(47), "source unchanged after the refusal")
c.done()
