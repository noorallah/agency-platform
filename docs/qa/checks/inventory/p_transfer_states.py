"""Probe: the stock-transfer document refuses every move that its state does not allow."""
from _inv import *
from _flow import *

c = Check("p_transfer_states")
w = World()
a, b2 = w.warehouse("A"), w.warehouse("B")
p = w.product()
w.stock_in(a["id"], p["id"], 100, 60)
ST = f"{INV}/stock-transfers"


def new(qty: str = "10") -> dict:
    """A draft transfer."""
    return must(w.admin.post(ST, {"transfer_date": w.today, "from_warehouse_id": a["id"], "to_warehouse_id": b2["id"],
                                  "lines": [{"product_id": p["id"], "quantity": qty}]}), "transfer")


def refused(label: str, answer: tuple[int, object]) -> None:
    """Must be a 4xx."""
    c.ok(400 <= answer[0] < 500, f"{label} is refused", (answer[0], message(answer[1])))


t = new()
refused("receiving a transfer that was never dispatched", w.admin.post(f"{ST}/{t['id']}/receive", {"lines": [{"line_number": 1, "received_quantity": "10"}]}))
c.eq(w.admin.post(f"{ST}/{t['id']}/dispatch", {})[0], 200, "dispatched")
refused("dispatching twice", w.admin.post(f"{ST}/{t['id']}/dispatch", {}))
c.eq(w.qty(p["id"], a["id"]), D(90), "second dispatch moved nothing more")
refused("receiving more than was sent", w.admin.post(f"{ST}/{t['id']}/receive", {"lines": [{"line_number": 1, "received_quantity": "11"}]}))
refused("damaged more than received", w.admin.post(f"{ST}/{t['id']}/receive", {"lines": [{"line_number": 1, "received_quantity": "5", "damaged_quantity": "6"}]}))
refused("a negative received quantity", w.admin.post(f"{ST}/{t['id']}/receive", {"lines": [{"line_number": 1, "received_quantity": "-1"}]}))
refused("an unknown line number", w.admin.post(f"{ST}/{t['id']}/receive", {"lines": [{"line_number": 9, "received_quantity": "1"}]}))
c.eq(D(w.rows(p["id"])[0]["in_transit_quantity"]) + D(w.rows(p["id"])[-1]["in_transit_quantity"]), D(10), "still 10 in transit after the refusals")
st, b = w.admin.post(f"{ST}/{t['id']}/receive", {"lines": [{"line_number": 1, "received_quantity": "10"}]})
c.eq(st, 200, "a full receipt")
refused("receiving twice", w.admin.post(f"{ST}/{t['id']}/receive", {"lines": [{"line_number": 1, "received_quantity": "10"}]}))
refused("cancelling a received transfer", w.admin.post(f"{ST}/{t['id']}/cancel", {"reason": "late"}))
refused("dispatching a received transfer", w.admin.post(f"{ST}/{t['id']}/dispatch", {}))
c.eq(w.qty(p["id"], b2["id"]), D(10), "destination holds exactly 10")
t2 = new("5")
c.eq(w.admin.post(f"{ST}/{t2['id']}/cancel", {"reason": "x"})[0], 200, "draft cancelled")
refused("cancelling twice", w.admin.post(f"{ST}/{t2['id']}/cancel", {"reason": "x"}))
refused("dispatching a cancelled transfer", w.admin.post(f"{ST}/{t2['id']}/dispatch", {}))
refused("a cancel without a reason", w.admin.post(f"{ST}/{new('1')['id']}/cancel", {"reason": "  "}))
# partial receipt: 6 of 10, nothing else said
t3 = new("10")
w.admin.post(f"{ST}/{t3['id']}/dispatch", {})
st, b = w.admin.post(f"{ST}/{t3['id']}/receive", {"lines": [{"line_number": 1, "received_quantity": "6"}]})
c.eq(st, 200, "a short receipt of 6 of 10")
got = data(b)
c.eq((D(got["lines"][0]["short_quantity"]), D(got["shortage_value"])), (D(4), D(240)), "the 4 that never arrived are the shortage, valued 240")
c.eq(w.qty(p["id"], a["id"]), D(80), "the source is not credited with the shortage")
c.done()
