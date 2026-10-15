"""Probe: a receipt is refused for more than the order has left, a draft receipt counts, and the stock stays put."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _buy import *

c = Check("p_buy_receipt_over_order")
a = admin()
sc = Scene(a)
pid = sc.product["id"]
order = sc.order(qty="10")
over = a.post(GR, sc.receipt_body(order, "11"))
c.ok(over[0] == 422 and "exceeds allowed quantity" in message(over[1]), "11 against an order of 10 is refused", (over[0], message(over[1])[:160]))
sc.receive(order, "6", complete=False)
second = a.post(GR, sc.receipt_body(order, "5"))
c.ok(second[0] == 422, "a draft of 6 already holds 6: 5 more is refused", (second[0], message(second[1])[:160]))
ok4 = a.post(GR, sc.receipt_body(order, "4"))
c.ok(ok4[0] in (200, 201), "the 4 that are left are accepted", (ok4[0], message(ok4[1])[:160]))
c.eq(stock(a, pid), D(0), "drafts move no stock")
neg = a.post(GR, sc.receipt_body(order, "-1"))
c.ok(neg[0] == 422, "a negative quantity is refused", (neg[0], message(neg[1])[:120]))
unapproved = sc.order(approve=False)
st, body = a.post(GR, sc.receipt_body(unapproved, "1"))
c.ok(st == 422, "a draft (unapproved) order cannot be received against", (st, message(body)[:160]))
c.done()
