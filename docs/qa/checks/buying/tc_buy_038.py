"""TC-BUY-038: reversing the payment leaves the bill approved and owing."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _buy import *

c = Check("tc_buy_038")
a = admin()
sc = Scene(a)
vid = sc.vendor["id"]
order = sc.order()
sc.receive(order, "4")
r6 = sc.receive(order, "6")
bill = sc.bill(r6, approve=False)
c.eq(a.post(f"{PI}/{bill['id']}/approve", {"payment": {"method": "CASH"}})[0], 200, "approve and pay")
pay = rows_of(a.get(f"{PAY}?vendor_id={vid}&page_size=50"))[0]
rev = a.post(f"{PAY}/{pay['id']}/reverse", {"reason": "check"})
c.eq(rev[0], 200, "the payment reverses like any other")
c.eq(must(a.get(f"{PI}/{bill['id']}"), "bill")["status"], "APPROVED", "the bill is still APPROVED")
c.eq(owing(a, vid, bill["id"]), D(708), "and owes 708.00 again")
rows = journal(a, pay["settlement_number"])
c.ok(any(entry_net(a, e).get("ACCOUNTS_PAYABLE") == D(-708) for e in rows), "the mirror journal: Dr Cash / Cr Trade Payables 708.00", len(rows))
c.done()
