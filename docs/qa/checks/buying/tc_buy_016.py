"""TC-BUY-016: one quantity picture per order line, and the billing status."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _buy import *

c = Check("tc_buy_016")
a = admin()
sc = Scene(a)
draft = sc.order(approve=False)
c.ok(draft["billing_status"] in (None, "NOT_INVOICED"), "a draft order shows no billing chip", draft["billing_status"])
order = sc.order()
r4 = sc.receive(order, "4")
r6 = sc.receive(order, "6")
bill6 = sc.bill(r6)
o = sc.reload(order)
line = o["lines"][0]
c.ok("PART" in str(o["billing_status"]).upper(), "header reads part billed", o["billing_status"])
c.eq([D(line[k]) for k in ("received_quantity", "invoiced_quantity", "pending_receipt_quantity", "to_invoice_quantity")],
     [D(10), D(6), D(0), D(4)], "received 10, billed 6, pending 0, to bill 4")
# a draft bill changes nothing
draft_bill = sc.bill(r4, approve=False)
line = sc.reload(order)["lines"][0]
c.eq((D(line["invoiced_quantity"]), D(line["to_invoice_quantity"])), (D(6), D(4)), "a draft bill changes nothing")
must(a.post(f"{PI}/{draft_bill['id']}/approve", {}), "approve")
o = sc.reload(order)
line = o["lines"][0]
c.eq((D(line["invoiced_quantity"]), D(line["to_invoice_quantity"])), (D(10), D(0)), "after approving: billed 10, to bill 0")
c.ok(str(o["billing_status"]).upper() in ("INVOICED", "FULLY_INVOICED", "BILLED"), "header reads billed", o["billing_status"])
sc.ret(r6, "2")
line = sc.reload(order)["lines"][0]
c.eq(D(line["returned_quantity"]), D(2), "Returned reads 2")
c.eq(D(line["to_invoice_quantity"]), D(0), "to bill is still 0 (the return is set against what was kept)")
c.done()
