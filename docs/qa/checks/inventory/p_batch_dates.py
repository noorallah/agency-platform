"""Probe: batch dates on a goods receipt: expiry before manufacturing, an expiry-tracked product with no date at all."""
from datetime import date, timedelta

from _inv import *
from _flow import *

c = Check("p_batch_dates")
w = World()
wh = w.warehouse()
d = date.fromisoformat(w.today)
iso = lambda n: (d + timedelta(days=n)).isoformat()
pb = w.product(goods_type="MEDICINE")
r = receive(w, wh["id"], pb["id"], 5, batch=f"D1{w.tag}")
c.eq(r["create"][0], 201, "receipt created")
c.ok(r.get("status", (0,))[0] in (409, 422), "a product that tracks expiry refuses a batch with no expiry and no manufacturing date",
     r.get("status", (0, ""))[0])
r = receive(w, wh["id"], pb["id"], 5, batch=f"D2{w.tag}", mfg=iso(10), expiry=iso(5))
c.ok(r["create"][0] in (409, 422) or r.get("status", (0,))[0] in (409, 422), "expiry before manufacturing is refused on a receipt",
     (r["create"][0], r.get("status", (0,))[0]))
r = receive(w, wh["id"], pb["id"], 5, batch="   ", mfg=iso(-1), expiry=iso(100))
c.ok(r["create"][0] in (409, 422) or r.get("status", (0,))[0] in (409, 422), "a blank batch number is refused", (r["create"][0], r.get("status", (0,))[0]))
st, b = w.admin.post("/api/v1/batch-serial/batches", {"product_id": pb["id"], "batch_number": "   "})
c.ok(st in (409, 422), "a blank batch number is refused on the batch master too", (st, message(b)))
c.eq(w.qty(pb["id"]), D(0), "no refused receipt stocked anything")
c.done()
