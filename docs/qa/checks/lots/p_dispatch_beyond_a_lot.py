"""Probe: dispatch more than one lot holds; a pick beyond the lot; a pick from another item's lot."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _lot import *  # noqa: F401,F403

c0 = Check("p_dispatch_beyond_a_lot")
api = lot_admin(); c = Ctx(api)
p, other = c.product("B"), c.product("O")
lots = two_lots(c, p, 10, 10)
two_lots(c, other, 5, 5)
# a pick of 12 from a lot that holds 10 is refused.
made = c.note([{"product": p, "qty": 12, "picks": [(lots["a"]["id"], 12)]}])
s, body = c.dispatch(made["note"]["id"])
c0.ok(s == 422, "a pick of 12 from a lot holding 10 is refused at dispatch", (s, message(body)[:200]))
# a pick naming another item's lot is refused.
ob = batch_of(c, other, "LOTA")
try:
    made = c.note([{"product": p, "qty": 2, "picks": [(ob["id"], 2)]}])
    s, body = c.dispatch(made["note"]["id"])
    c0.ok(s == 422, "a pick from another item's lot is refused", (s, message(body)[:200]))
except SystemExit as stop:
    c0.ok("PRECONDITION" in str(stop), "a pick from another item's lot is refused when the note is written", str(stop)[:200])
c0.eq(c.stock(p), D(20), "nothing left the lots")
# no pick, 15 units across two lots: 10 from LOTA at 40, 5 from LOTB at 42 (a product of its own,
# since the refused notes above still hold reservations).
p = c.product("C")
two_lots(c, p, 10, 10)
made = c.sell([{"product": p, "qty": 15}])
c.bill(made["note"])
rows = lotmap(c, p)
c0.eq((D(rows.get("LOTA", {}).get("quantity", 0)), D(rows["LOTB"]["quantity"])), (D(0), D(5)), "15 with no pick empties LOTA then takes 5 of LOTB")
s, body = api.get("/api/v1/sales-invoices/reports/margin-by-lot")
m = {r["batch_number"]: D(r["cost"]) for r in data(body) if r["product_id"] == p["id"]}
c0.eq(m, {"LOTA": D(400), "LOTB": D(210)}, "each lot costs its own units (400 and 210)")
c0.done()
