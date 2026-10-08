"""Probe: a second order that exceeds stock must not starve the dispatch of an earlier order that stock covers (D-STK-39)."""
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
# An order holds its whole quantity; the part nothing covers is the back order.
c.eq(D(r["reserved_quantity"]), D(7), "both orders hold their whole quantity (3 + 4 with 4 held)")
d = w.admin.post(f"/api/v1/delivery-notes/{s2['note']['id']}/dispatch", {})
c.ok(400 <= d[0] < 500, "the later order (4) waits: three of the four stand behind the earlier one", (d[0], message(d[1])))
d = w.admin.post(f"/api/v1/delivery-notes/{s1['note']['id']}/dispatch", {})
c.eq(d[0], 200, "the first order (3 of 4 held) still dispatches: " + message(d[1]))
r = w.rows(p["id"])[0]
c.eq((D(r["current_quantity"]), D(r["reserved_quantity"])), (D(1), D(4)), "one is left on the shelf, the later order's four still held")
d = w.admin.post(f"/api/v1/delivery-notes/{s2['note']['id']}/dispatch", {})
c.ok(400 <= d[0] < 500, "the later order still cannot ship four from one", (d[0], message(d[1])))
c.done()
