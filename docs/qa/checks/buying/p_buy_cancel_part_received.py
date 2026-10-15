"""Probe: an order a live receipt continues is closed, not cancelled (buying round 1, B-2)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _buy import *

c = Check("p_buy_cancel_part_received")
a = admin()
sc = Scene(a)
order = sc.order(qty="10")
draft = sc.receive(order, "4", complete=False)
st, body = a.post(f"{PO}/{order['id']}/cancel", {"reason": "probe"})
c.ok(st == 422 and draft["grn_number"] in message(body), "a draft receipt stops the cancel, by number", (st, message(body)[:160]))
must(a.post(f"{GR}/{draft['id']}/cancel", {"reason": "probe"}), "draft cancel")
sc.receive(order, "6")
st, body = a.post(f"{PO}/{order['id']}/cancel", {"reason": "probe"})
c.ok(st == 422 and "close the order" in message(body), "six of ten received: cancel refused", (st, message(body)[:160]))
c.eq(sc.reload(order)["status"], "PARTIALLY_RECEIVED", "the order is untouched")
must(a.post(f"{PO}/{order['id']}/close", {"reason": "probe"}), "close")
c.eq(sc.reload(order)["status"], "CLOSED", "closing stops the rest")
spare = sc.order(qty="5")
must(a.post(f"{PO}/{spare['id']}/cancel", {"reason": "probe"}), "cancel with nothing raised")
c.eq(sc.reload(spare)["status"], "CANCELLED", "an order nothing continues still cancels")
c.done()
