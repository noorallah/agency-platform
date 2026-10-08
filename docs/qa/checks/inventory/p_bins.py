"""Probe (round 3): stock held in a bin, and an order owed more than the bin holds."""
from _r3 import *

c = Check("p_bins")
w = World()
wh = w.warehouse()["id"]
node = must(
    w.admin.post("/api/v1/warehouses/storage-nodes", {"warehouse_id": wh, "node_type": "BIN", "code": f"B{w.tag}", "name": f"Bin {w.tag}"}),
    "bin",
)
p = w.product()["id"]
w.opening(wh, [{"product_id": p, "quantity": "4", "unit_cost": "60", "storage_node_id": node["id"]}])
row = w.rows(p)[0]
c.eq((row["storage_node_id"], D(row["current_quantity"])), (node["id"], D(4)), "opening stock lands in the bin named on its line")
so = order(w, wh, p, 10)
# D-STK-54 (open, Low): a note line naming no bin does not see what a bin holds, and does not say so.
st, msg = ship(w, so, wh, 4)
c.ok(st == 200 or "bin" in msg.lower() or node["code"].lower() in msg.lower(),
     "a note naming no bin ships what the bin holds, or says the goods are in a bin (D-STK-54)", (st, msg))
if st != 200:
    st, msg = ship(w, so, wh, 4, storage_node_id=node["id"])
    c.eq(st, 200, "the note naming the bin ships the four, the order being owed ten: " + msg)
c.eq(w.qty(p, wh), D(0), "the bin is empty")
c.eq(w.qty(p, wh, "reserved_quantity"), D(6), "six are still owed")
c.done()
