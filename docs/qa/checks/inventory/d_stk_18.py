"""D-STK-18: the batch summary card counts an emptied batch as near expiry; the dashboard and the alerts count only batches holding stock."""
from datetime import date, timedelta

from _inv import *
from _flow import *

c = Check("d_stk_18")
w = World()
wh = w.warehouse()
d = date.fromisoformat(w.today)
pb = w.product(goods_type="MEDICINE")
BS, DASH = "/api/v1/batch-serial/batches/summary", "/api/v1/batch-serial/batches/expiry-dashboard"
s0, d0, a0 = data(w.admin.get(BS)[1]), data(w.admin.get(DASH)[1]), data(w.admin.get(f"{INV}/alerts")[1])
r = receive(w, wh["id"], pb["id"], 5, batch=f"N{w.tag}", mfg=(d - timedelta(days=100)).isoformat(), expiry=(d + timedelta(days=20)).isoformat())
c.eq(r["status"][0], 200, "near-expiry batch received")
s1, d1 = data(w.admin.get(BS)[1]), data(w.admin.get(DASH)[1])
c.eq(s1["near_expiry"] - s0["near_expiry"], 1, "with stock: the card counts it")
c.eq(d1["expire_in_30_days"] + d1["expire_in_7_days"] - d0["expire_in_30_days"] - d0["expire_in_7_days"], 1, "with stock: the dashboard counts it")
s = sell_and_dispatch(w, wh["id"], pb["id"], 5)
c.eq(s["dispatch"][0], 200, "all 5 dispatched (the batch is empty)")
s2, d2 = data(w.admin.get(BS)[1]), data(w.admin.get(DASH)[1])
dash_delta = d2["expire_in_30_days"] + d2["expire_in_7_days"] - d0["expire_in_30_days"] - d0["expire_in_7_days"]
c.eq(dash_delta, 0, "emptied: the dashboard no longer counts it")
c.eq(s2["near_expiry"] - s0["near_expiry"], dash_delta, "emptied: the summary card agrees with the dashboard")
c.done()
