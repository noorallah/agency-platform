"""TC-BUY-094: the same goods go back once, whichever document the return names."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _buy import *

c = Check("tc_buy_094")
a = admin()
sc = Scene(a)
pid = sc.product["id"]
vid = sc.vendor["id"]
order = sc.order()
sc.receive(order, "4")
r6 = sc.receive(order, "6")
bill = sc.bill(r6)
# (1) 6 off the bill completes
ret1 = sc.ret(bill, "6", kind="PURCHASE_INVOICE")
c.eq(D(ret1["grand_total"]), D(708), "(1) the return off the bill is 708.00")
rj = journal(a, ret1["return_number"])
c.ok(len(rj) >= 1, "the return has a journal")
if rj:
    net = entry_net(a, rj[0])
    c.eq(net.get("ACCOUNTS_PAYABLE"), D(708), "Dr Trade Payables 708.00")
    c.eq(net.get("INVENTORY"), D(-600), "Cr Inventory 600.00")
    c.eq([net.get("INPUT_TAX_CGST"), net.get("INPUT_TAX_SGST")], [D(-54), D(-54)], "Cr Input CGST 54 and SGST 54")
# (2) the receipt of 6 that bill billed: 4 more is refused
st, body = a.post(PR, sc.return_body(r6, "4"))
c.ok(st == 422 and "can still send back 0" in message(body) and "already gone back against the supplier bill" in message(body),
     "(2) 4 off the receipt that was billed is refused at Save", (st, message(body)[:240]))
day = today().isoformat()
status, stm = a.get(f"/api/v1/vendors/{vid}/statement?from_date={day}&to_date={day}")
c.eq(status, 200, "the statement answers")
lines = data(stm)["lines"]
c.eq([x["transaction_type"] for x in lines], ["BILL", "PURCHASE_RETURN"], "the statement shows the bill and one return against it, never two")
c.eq([D(x["credit"]) for x in lines[:1]] + [D(x["debit"]) for x in lines[1:]], [D(708), D(708)], "708.00 billed, 708.00 returned")
# (3) second order: bill, then 6 off its bill
o2 = sc.order()
g2 = sc.receive(o2, "10")
b2 = sc.bill(g2)
c.eq(D(b2["grand_total"]), D(1180), "the second bill is 1,180.00")
ret3 = sc.ret(b2, "6", kind="PURCHASE_INVOICE")
c.eq(D(ret3["grand_total"]), D(708), "(3) 6 off its bill completes at 708.00")
# (4) 5 off its receipt is refused
st, body = a.post(PR, sc.return_body(g2, "5"))
c.ok(st == 422 and "can still send back 4" in message(body) and "already gone back against the supplier bill" in message(body),
     "(4) 5 off the receipt is refused: only 4 are left", (st, message(body)[:240]))
# (5) 4 off the receipt saves a draft at 472.00; 1 more off the bill is refused
draft4 = must(a.post(PR, sc.return_body(g2, "4")), "draft of 4")
c.eq(D(draft4["grand_total"]), D(472), "(5) 4 off the receipt is accepted at 472.00")
st, body = a.post(PR, sc.return_body(b2, "1", kind="PURCHASE_INVOICE"))
c.ok(st == 422 and "can still send back 0" in message(body) and "already gone back against the goods receipt" in message(body),
     "a draft already holds its quantity: 1 more off the bill is refused", (st, message(body)[:240]))
# (6) approve and complete the 4
must(a.post(f"{PR}/{draft4['id']}/approve", {}), "approve")
done4 = must(a.post(f"{PR}/{draft4['id']}/complete", {}), "complete")
c.eq(done4["status"], "COMPLETED", "(6) the return of 4 completes")
before = stock(a, pid)
# (7) cancel it: the quantity is freed and the stock comes back
cancel = a.post(f"{PR}/{draft4['id']}/cancel", {"reason": "check"})
c.eq(cancel[0], 200, "(7) the completed return of 4 cancels")
c.eq(stock(a, pid), before + 4, "the 4 are on hand again")
st, body = a.post(PR, sc.return_body(b2, "5", kind="PURCHASE_INVOICE"))
c.ok(st == 422 and "can still send back 4" in message(body), "5 off the bill is refused, 4 left", (st, message(body)[:200]))
again = a.post(PR, sc.return_body(b2, "4", kind="PURCHASE_INVOICE"))
c.ok(again[0] in (200, 201), "4 off the bill is accepted", (again[0], message(again[1])[:200]))
c.done()
