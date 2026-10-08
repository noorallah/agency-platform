"""Probe (round 3): round 2's refusals reach a storekeeper as they reach the firm admin (D-STK-44, D-STK-49)."""
from _r3 import *

c = Check("p_roles_round_2")
w = World()
store = client("store")
wh = w.warehouse()["id"]
paint = w.product(goods_type="PAINT")["id"]
plain = w.product()["id"]
w.stock_in(wh, plain, 10)
base = {"branch_id": w.branch_id, "product_id": plain, "transaction_date": w.today, "warehouse_id": wh, "quantity": "1", "reason": "DAMAGE",
        "reference_number": f"RR{w.tag}"}
st, body = store.post(f"{INV}/write-offs", base)
c.eq(st, 201, "the storekeeper writes one off under a reference: " + message(body))
c.refused(store.post(f"{INV}/write-offs", base), 409, "already exists", "the second write-off under the same reference, by the storekeeper")
c.eq(w.qty(plain, wh), D(9), "one unit left the shelf, not two")
batch = {"product_id": paint, "warehouse_id": wh, "batch_number": f"RM{w.tag}", "mrp": "50", "selling_price": "90"}
c.refused(store.post("/api/v1/batch-serial/batches", batch), 422, "cannot exceed the MRP", "a batch priced above its MRP, by the storekeeper")
st, body = store.post("/api/v1/batch-serial/batches", {**batch, "selling_price": "45"})
c.eq(st, 201, "the same batch at 45 under an MRP of 50 is saved: " + message(body))
c.done()
