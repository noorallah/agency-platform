"""Probe: serial-tracked stock (tracking comes from the product's goods type): receipt, dispatch with serials, refusals."""
from _inv import *
from _flow import *

c = Check("p_serial_flow")
w = World()
wh = w.warehouse()
S = "/api/v1/batch-serial/serials"
tag = w.tag


def fresh(n: int) -> tuple[dict, list[str], dict]:
    """A serial-tracked product with n serials received, and the serial rows by number."""
    prod = w.product(goods_type="ELECTRONICS")
    numbers = [f"E{i}{suffix(4)}" for i in range(n)]
    r = receive(w, wh["id"], prod["id"], n, serials=numbers)
    c.eq(r["status"][0], 200, f"{n} serials received")
    rows = {x["serial_number"]: x for x in all_rows(w.admin, f"{S}?product_id={prod['id']}")}
    return prod, numbers, rows


prod, nums, rows = fresh(4)
c.eq({x["status"] for x in rows.values()}, {"AVAILABLE"}, "received serials are AVAILABLE")
c.eq(w.qty(prod["id"]), D(4), "stock 4")
# a receipt of a serial-tracked unit with the wrong number of serials
p2 = w.product(goods_type="ELECTRONICS")
r = receive(w, wh["id"], p2["id"], 3, serials=["W1" + suffix(4), "W2" + suffix(4)])
c.eq(r["status"][0], 422, "3 units with 2 serials is refused at completion")
c.eq(w.qty(p2["id"]), D(0), "and nothing was stocked")
# dispatch refusals (each on its own product so a refused note holds no reservation against the next)
for label, n_take in (("no serials", 0), ("one serial for two", 1)):
    pp, ns, rr = fresh(3)
    ids = [rr[x]["id"] for x in ns[:n_take]]
    s = sell_and_dispatch(w, wh["id"], pp["id"], 2, serial_ids=ids or None)
    c.eq(s["dispatch"][0], 422, f"dispatch with {label} is refused: {message(s['dispatch'][1])[:90]}")
    c.eq(w.qty(pp["id"]), D(3), f"{label}: stock unchanged")
pp, ns, rr = fresh(3)
other_p, other_ns, other_rr = fresh(1)
s = sell_and_dispatch(w, wh["id"], pp["id"], 1, serial_ids=[other_rr[other_ns[0]]["id"]])
c.eq(s.get("note_create", (0,))[0], 422, "another product's serial on the note is refused")
# good dispatch
pp, ns, rr = fresh(3)
s = sell_and_dispatch(w, wh["id"], pp["id"], 2, serial_ids=[rr[ns[0]]["id"], rr[ns[1]]["id"]])
c.eq(s["dispatch"][0], 200, "dispatch with the right serials: " + message(s["dispatch"][1])[:90])
now = {x["serial_number"]: x["status"] for x in all_rows(w.admin, f"{S}?product_id={pp['id']}")}
c.ok(now[ns[0]] != "AVAILABLE" and now[ns[1]] != "AVAILABLE", "dispatched serials leave AVAILABLE", now)
c.eq(now[ns[2]], "AVAILABLE", "the undispatched serial stays AVAILABLE")
c.eq(w.qty(pp["id"]), D(1), "stock 1")
st, b = w.admin.get(f"{S}/{rr[ns[0]]['id']}/trail")
c.ok(st == 200 and len(data(b).get("events", [])) >= 2, "the trail shows receipt and dispatch", (st, str(data(b))[:100]))
# the same serial cannot go again
s2 = sell_and_dispatch(w, wh["id"], pp["id"], 1, serial_ids=[rr[ns[0]]["id"]])
c.ok(s2.get("note_create", (0,))[0] in (409, 422) or s2.get("dispatch", (0,))[0] in (409, 422), "an already dispatched serial cannot be picked again",
     {k: (v[0] if isinstance(v, tuple) else "") for k, v in s2.items()})
c.eq(w.qty(pp["id"]), D(1), "stock still 1")
c.done()
