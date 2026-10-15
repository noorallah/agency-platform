"""Probe: a payment cannot allocate more than a bill owes or than its own amount; a fully received order cannot be cancelled."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _buy import *

c = Check("p_buy_payment_edges")
a = admin()
sc = Scene(a)
vid = sc.vendor["id"]
order = sc.order(qty="10")
rc = sc.receive(order, "6")
bill = sc.bill(rc)
day = today().isoformat()
base = {"party_id": vid, "settlement_date": day, "method": "BANK"}
over = a.post(PAY, {**base, "amount": "800", "allocations": [{"invoice_id": bill["id"], "amount": "800"}]})
c.ok(over[0] == 422, "800 allocated to a bill of 708 is refused", (over[0], message(over[1])[:200]))
more = a.post(PAY, {**base, "amount": "100", "allocations": [{"invoice_id": bill["id"], "amount": "200"}]})
c.ok(more[0] == 422, "allocating more than the payment's own amount is refused", (more[0], message(more[1])[:200]))
c.ok(a.post(PAY, {**base, "amount": "0", "allocations": []})[0] == 422, "a payment of 0 is refused")
c.ok(a.post(PAY, {**base, "amount": "10", "settlement_date": (today() + timedelta(days=3)).isoformat()})[0] == 422, "a payment dated in the future is refused")
c.eq(owing(a, vid, bill["id"]), D(708), "nothing was recorded: the bill still owes 708.00")
full = sc.order(qty="4")
sc.receive(full, "4")
gone = a.post(f"{PO}/{full['id']}/cancel", {"reason": "check"})
c.refused(gone, 422, "Received purchase orders cannot be cancelled", "a fully received order cannot be cancelled")
fresh = sc.order()
c.eq(a.post(f"{PO}/{fresh['id']}/cancel", {"reason": "check"})[0], 200, "an order nothing was received against cancels")
c.done()
