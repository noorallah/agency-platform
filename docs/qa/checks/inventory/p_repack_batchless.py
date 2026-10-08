"""Probe (round 3): a repack that produces a batch-tracked product names the batch it goes into (D-STK-53, open)."""
from _r3 import *

c = Check("p_repack_batchless")
w = World()
wh = w.warehouse()["id"]
plain = w.product()
w.stock_in(wh, plain["id"], 5)
med = w.product(goods_type="MEDICINE")
st, body = w.admin.post(f"{INV}/repacks", {"repack_date": w.today, "branch_id": w.branch_id, "warehouse_id": wh, "lines": [
    {"kind": "CONSUME", "product_id": plain["id"], "quantity": "1"}, {"kind": "PRODUCE", "product_id": med["id"], "quantity": "1"}]})
held = by_batch(w, med["id"])
c.ok(st == 422 or None not in held, "a batch-tracked product is not produced into stock with no batch", (st, message(body), held))
c.done()
