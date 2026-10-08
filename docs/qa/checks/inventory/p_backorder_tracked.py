"""Probe (round 3): a back order beside batches, beside batches a person chose, and beside serial units."""
from _r3 import *
from _flow import receive

c = Check("p_backorder_tracked")
w = World()
wh = w.warehouse()["id"]

# Batches: four held in A and an order for ten; five arrive in B and a later order takes three of them.
p = w.product(goods_type="MEDICINE")["id"]
receive(w, wh, p, 4, batch=f"A{w.tag}", mfg=iso(w, -30), expiry=iso(w, 200))
early = order(w, wh, p, 10)
receive(w, wh, p, 5, batch=f"B{w.tag}", mfg=iso(w, -10), expiry=iso(w, 300))
late = order(w, wh, p, 3)
c.eq(by_batch(w, p, "reserved_quantity"), {f"A{w.tag}": D(4), f"B{w.tag}": D(3), None: D(6)},
     "each order holds real stock where it found it; the back order sits on the row with no batch")
st, msg = ship(w, early, wh, 6)
c.eq(st, 200, "the earlier order ships its four of A and the two free of B: " + msg)
c.eq(by_batch(w, p), {f"A{w.tag}": D(0), f"B{w.tag}": D(3), None: D(0)}, "the three the later order holds stay on the shelf")
st, msg = ship(w, late, wh, 3)
c.eq(st, 200, "the later order ships the three it holds: " + msg)
st, msg = ship(w, early, wh, 1)
c.ok(st != 200, "the earlier order does not ship from an empty shelf", (st, msg))
c.ok(all(v >= 0 for v in by_batch(w, p).values()), "no batch went below nothing", by_batch(w, p))

# A person chooses the batch: a later order cannot take the goods behind an earlier one by naming them.
q = w.product(goods_type="MEDICINE")["id"]
receive(w, wh, q, 4, batch=f"P{w.tag}", mfg=iso(w, -30), expiry=iso(w, 200))
early, late = order(w, wh, q, 10), order(w, wh, q, 2)
bid = next(r for r in w.rows(q) if r.get("batch_number"))["batch_id"]
st, msg = ship(w, late, wh, 2, batches=[{"batch_id": bid, "quantity": "2"}])
c.ok(st != 200, "a later order naming the batch does not jump the earlier one", (st, msg))
c.eq(w.qty(q, wh), D(4), "and the four are still there")
st, msg = ship(w, early, wh, 4, batches=[{"batch_id": bid, "quantity": "4"}])
c.eq(st, 200, "the earlier order ships the four, naming the batch: " + msg)
c.eq(w.qty(q, wh), D(0), "nothing is left")

# Serial units: two held, an order for five and a later one for one.
s = w.product(goods_type="ELECTRONICS")["id"]
receive(w, wh, s, 2, serials=[f"U{i}{suffix(4)}" for i in range(2)])
ids = [x["id"] for x in units(w, s).values()]
early, late = order(w, wh, s, 5), order(w, wh, s, 1)
st, msg = ship(w, late, wh, 1, serial_ids=ids[:1])
c.ok(st != 200, "a later order naming a unit does not jump the earlier one", (st, msg))
c.eq({x["status"] for x in units(w, s).values()}, {"AVAILABLE"}, "both units still read AVAILABLE")
st, msg = ship(w, early, wh, 2, serial_ids=ids)
c.eq(st, 200, "the earlier order ships the two units: " + msg)
c.eq({x["status"] for x in units(w, s).values()}, {"SOLD"}, "both units read SOLD")
c.eq((w.qty(s, wh), w.qty(s, wh, "reserved_quantity")), (D(0), D(4)), "nothing held; three of the first order and one of the second still owed")
c.done()
