"""Probe: tracking follows the product's goods type: untracked, batch-tracked and expiry-tracked products on receipt, quarantine and write-off."""
from datetime import date, timedelta

from _inv import *
from _flow import *

c = Check("p_tracking")
w = World()
wh = w.warehouse()
d = date.fromisoformat(w.today)
iso = lambda n: (d + timedelta(days=n)).isoformat()
plain = w.product()
medicine = w.product(goods_type="MEDICINE")
paint = w.product(goods_type="PAINT")  # batch, no expiry
c.eq((plain["track_batch"], plain["track_expiry"], plain["track_serial"]), (False, False, False), "a product with no goods type tracks nothing")
c.eq((medicine["track_batch"], medicine["track_expiry"]), (True, True), "a Medicine product tracks batch and expiry")
c.eq((paint["track_batch"], paint["track_expiry"]), (True, False), "a Paint product tracks batch only")
r = receive(w, wh["id"], plain["id"], 3, batch=f"X{w.tag}")
# D-STK-43 (owner's rule, round 4): the number is ignored, the receipt goes through, no batch is made.
c.eq(r.get("status", (0,))[0], 200, "a receipt naming a batch for a product that tracks none still goes through")
c.eq([(x["batch_number"], D(x["current_quantity"])) for x in w.rows(plain["id"])], [(None, D(3))],
     "the goods are on the product's own row and no batch was made")
r = receive(w, wh["id"], plain["id"], 3, serials=["S1" + w.tag, "S2" + w.tag, "S3" + w.tag])
c.ok(r["create"][0] in (409, 422) or r.get("status", (0,))[0] in (409, 422), "serial numbers on a product that does not track serials are refused",
     (r["create"][0], r.get("status", (0, ""))[0]))
r = receive(w, wh["id"], paint["id"], 3, batch=f"P{w.tag}", expiry=iso(100))
c.ok(r["create"][0] in (409, 422) or r.get("status", (0,))[0] in (409, 422), "an expiry on a batch-only product is refused",
     (r["create"][0], r.get("status", (0, ""))[0]))
r = receive(w, wh["id"], paint["id"], 3, batch=f"P{w.tag}")
c.eq(r.get("status", (0,))[0], 200, "a batch-only product takes a batch")
r = receive(w, wh["id"], medicine["id"], 6, batch=f"M{w.tag}", mfg=iso(-5), expiry=iso(300))
c.eq(r.get("status", (0,))[0], 200, "a Medicine product takes batch + expiry")
# write-off, hold and transfer of a batch-tracked product need the batch named when several exist
r = receive(w, wh["id"], medicine["id"], 4, batch=f"N{w.tag}", mfg=iso(-5), expiry=iso(200))
base = {"branch_id": w.branch_id, "product_id": medicine["id"], "transaction_date": w.today, "warehouse_id": wh["id"]}
bm = next(x for x in w.rows(medicine["id"]) if x["batch_number"] == f"M{w.tag}")
st, b = w.admin.post(f"{INV}/write-offs", {**base, "quantity": "1", "reason": "EXPIRY", "reference_number": f"W{w.tag}", "batch_id": bm["batch_id"]})
c.eq(st, 201, "a write-off naming the batch")
rows = {x["batch_number"]: D(x["current_quantity"]) for x in w.rows(medicine["id"])}
c.eq(rows, {f"M{w.tag}": D(5), f"N{w.tag}": D(4)}, "only the named batch lost the unit")
st, b = w.admin.post(f"{INV}/write-offs", {**base, "quantity": "6", "reason": "EXPIRY", "reference_number": f"W2{w.tag}", "batch_id": bm["batch_id"]})
c.ok(400 <= st < 500, "writing off more than the named batch holds is refused (the other batch has stock but is not the one named)", (st, message(b)))
st, b = w.admin.post(f"{INV}/quarantine", {**base, "action": "HOLD", "quantity": "2", "reference_number": f"Q{w.tag}", "batch_id": bm["batch_id"]})
c.eq(st, 201, "quarantine of a batch")
st, b = w.admin.post(f"{INV}/quarantine", {**base, "action": "RELEASE", "quantity": "5", "reference_number": f"R{w.tag}", "batch_id": bm["batch_id"]})
c.ok(400 <= st < 500, "releasing more than is held in quarantine is refused", (st, message(b)))
st, b = w.admin.post(f"{INV}/quarantine", {**base, "action": "RELEASE", "quantity": "2", "reference_number": f"R2{w.tag}", "batch_id": bm["batch_id"]})
c.eq(st, 201, "releasing what was held")
c.done()
