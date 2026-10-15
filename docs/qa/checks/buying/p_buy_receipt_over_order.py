"""Probe: a receipt is refused for more than the order has left, a second receipt over the rest is refused at Complete."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _buy import *

c = Check("p_buy_receipt_over_order")
a = admin()
sc = Scene(a)
pid = sc.product["id"]
order = sc.order(qty="10")
over = a.post(GR, sc.receipt_body(order, "11"))
c.ok(over[0] == 422 and "exceeds allowed quantity" in message(over[1]), "11 against an order of 10 is refused", (over[0], message(over[1])[:160]))
# Decided 2026-10-15 (buying round 1, B-1): a draft receipt brings nothing
# in, so it holds nothing; the order's remainder is checked at Complete, the
# ERPNext / Zoho rule.
first = sc.receive(order, "6", complete=False)
second = must(a.post(GR, sc.receipt_body(order, "5")), "second draft")
c.eq(stock(a, pid), D(0), "drafts move no stock")
must(a.post(f"{GR}/{first['id']}/complete", {}), "first complete")
late = a.post(f"{GR}/{second['id']}/complete", {})
c.ok(late[0] == 422, "with 6 in, completing 5 more of 10 is refused", (late[0], message(late[1])[:160]))
c.eq(stock(a, pid), D(6), "only the first receipt's 6 are in")
neg = a.post(GR, sc.receipt_body(order, "-1"))
c.ok(neg[0] == 422, "a negative quantity is refused", (neg[0], message(neg[1])[:120]))
unapproved = sc.order(approve=False)
st, body = a.post(GR, sc.receipt_body(unapproved, "1"))
c.ok(st == 422, "a draft (unapproved) order cannot be received against", (st, message(body)[:160]))
c.done()
