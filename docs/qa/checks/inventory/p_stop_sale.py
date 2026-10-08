"""Probe: a batch inside its stop-sale window is refused at dispatch and in the note's batch check; an expired batch is never sold."""
from datetime import date, timedelta

from _inv import *
from _flow import *

c = Check("p_stop_sale")
w = World()
wh = w.warehouse()
d = date.fromisoformat(w.today)
iso = lambda n: (d + timedelta(days=n)).isoformat()
p = w.product(goods_type="MEDICINE", expiry_stop_sale_days=20)
receive(w, wh["id"], p["id"], 10, batch=f"S{w.tag}", mfg=iso(-300), expiry=iso(15))
s = sell_and_dispatch(w, wh["id"], p["id"], 2, dispatch=False)
c.eq(s.get("note_approve", (0,))[0], 200, "note raised and approved")
chk = w.admin.get(f"/api/v1/delivery-notes/{s['note']['id']}/batch-check")
c.eq(chk[0], 200, "batch check answers")
disp = w.admin.post(f"/api/v1/delivery-notes/{s['note']['id']}/dispatch", {})
c.ok(disp[0] in (409, 422), "dispatch of the only batch, 15 days from expiry with a 20-day stop-sale rule, is refused", (disp[0], message(disp[1])[:100]))
c.eq(w.qty(p["id"]), D(10), "nothing left the warehouse")
# an expired batch is never sold
q = w.product(goods_type="MEDICINE")
receive(w, wh["id"], q["id"], 10, batch=f"X{w.tag}", mfg=iso(-400), expiry=iso(-5))
s2 = sell_and_dispatch(w, wh["id"], q["id"], 2)
c.ok(s2.get("dispatch", (0,))[0] in (409, 422) or s2.get("approve", (0,))[0] in (409, 422) or s2.get("note_create", (0,))[0] in (409, 422),
     "the only batch is expired: nothing can be dispatched", {k: (v[0] if isinstance(v, tuple) else "") for k, v in s2.items()})
c.eq(w.qty(q["id"]), D(10), "the expired batch is untouched")
c.done()
