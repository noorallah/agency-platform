"""Probe: a second order that exceeds stock must not starve the dispatch of an earlier order that stock covers."""
from _inv import *
from _flow import *

c = Check("p_overreserve")
w = World()
wh = w.warehouse()
p = w.product()
w.stock_in(wh["id"], p["id"], 4)
s1 = sell_and_dispatch(w, wh["id"], p["id"], 3, dispatch=False)
s2 = sell_and_dispatch(w, wh["id"], p["id"], 4, dispatch=False)
r = w.rows(p["id"])[0]
c.ok(D(r["reserved_quantity"]) <= D(r["current_quantity"]), "reserved never exceeds what is held",
     f"reserved {r['reserved_quantity']} on hand {r['current_quantity']}")
d = w.admin.post(f"/api/v1/delivery-notes/{s1['note']['id']}/dispatch", {})
c.eq(d[0], 200, "the first order (3 of 4 held) still dispatches: " + message(d[1]))
c.done()
