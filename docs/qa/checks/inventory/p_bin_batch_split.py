"""Probe (round 4): a note naming no bin and no batch ships batch-tracked goods held partly in a bin (D-STK-54).

Five of a batch on the warehouse's own row and three of an earlier-expiring batch in a bin: a note for six takes
the batch that expires first, bin or not, then the later one, and each movement leaves from the place it was drawn."""
from _r3 import *

c = Check("p_bin_batch_split")
w = World()
wh = w.warehouse()["id"]
node = must(
    w.admin.post("/api/v1/warehouses/storage-nodes", {"warehouse_id": wh, "node_type": "BIN", "code": f"B{w.tag}", "name": f"Bin {w.tag}"}),
    "bin",
)
med = w.product(goods_type="MEDICINE")["id"]
a, b = f"NA{w.tag}", f"NB{w.tag}"
w.opening(wh, [
    {"product_id": med, "quantity": "3", "unit_cost": "60", "batch_number": a, "expiry_date": iso(w, 100), "storage_node_id": node["id"]},
    {"product_id": med, "quantity": "5", "unit_cost": "60", "batch_number": b, "expiry_date": iso(w, 300)},
])
c.eq(by_batch(w, med), {a: D(3), b: D(5)}, "three of the early batch in the bin, five of the later on the warehouse's own row")
so = order(w, wh, med, 8)
st, msg = ship(w, so, wh, 6)
c.eq(st, 200, "a note for six naming no bin and no batch is dispatched: " + msg)
rows = w.rows(med)
c.ok(all(D(r["current_quantity"]) >= 0 for r in rows), "no row went below zero", [(r.get("batch_number"), r["current_quantity"]) for r in rows])
c.eq(sum(D(r["current_quantity"]) for r in rows), D(2), "two are left of the eight")
c.eq(by_batch(w, med), {a: D(0), b: D(2)}, "the batch expiring first left whole from the bin, then three of the later batch")
left = next(r for r in rows if r.get("batch_number") == b)
c.eq(left["storage_node_id"], None, "what is left is on the warehouse's own row")
out = [m for m in w.ledger(med) if D(m["current_quantity_delta"]) < 0]
c.eq(sorted(D(m["current_quantity_delta"]) for m in out), [D(-3), D(-3)], "two movements, one from each place")
c.eq(sum(D(r["reserved_quantity"]) for r in rows), D(2), "the two still owed stay reserved")
st, msg = ship(w, so, wh, 2)
c.eq(st, 200, "the rest ships: " + msg)
c.eq(sum(D(r["current_quantity"]) for r in w.rows(med)), D(0), "and nothing is left")
c.done()
