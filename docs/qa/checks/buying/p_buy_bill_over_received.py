"""Probe: a supplier bill cannot bill more than was received, across bills together; a refused approve-and-pay leaves a draft."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _buy import *

c = Check("p_buy_bill_over_received")
a = admin()
sc = Scene(a)
order = sc.order(qty="10")
rc = sc.receive(order, "6")
over = a.post(PI, sc.bill_body(rc, qty="7"))
c.ok(over[0] == 422 and "left to bill" in message(over[1]), "7 billed on a receipt of 6 is refused", (over[0], message(over[1])[:200]))
first = sc.bill(rc, qty="4", approve=False)
second = a.post(PI, sc.bill_body(rc, qty="3"))
c.ok(second[0] == 422, "a draft bill of 4 already holds 4: 3 more is refused", (second[0], message(second[1])[:200]))
c.eq(a.post(PI, sc.bill_body(rc, qty="2"))[0], 201, "the 2 that are left are accepted")
c.eq(must(a.get(f"{PI}/{first['id']}"), "bill")["status"], "DRAFT", "the first bill is untouched")
c.refused(a.post(f"{PI}/{first['id']}/approve", {"payment": {"method": "BANK", "amount": "9999"}}), 422, "owes", "paying more than the bill owes at approval")
c.eq(must(a.get(f"{PI}/{first['id']}"), "bill")["status"], "DRAFT", "the bill is still a draft after the refusal")
c.done()
