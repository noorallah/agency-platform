"""TC-BUY-008: paying the supplier."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _buy import *

c = Check("tc_buy_008")
a = admin()
sc = Scene(a)
order = sc.order()
sc.receive(order, "4")
r6 = sc.receive(order, "6")
bill = sc.bill(r6)
c.eq(owing(a, sc.vendor["id"], bill["id"]), D(708), "the bill owes 708.00")
listed = rows_of(a.get(f"{PAY}/outstanding?vendor_id={sc.vendor['id']}"))
c.ok(any(r.get("id") == bill["id"] or r.get("invoice_id") == bill["id"] for r in listed), "the bill is on the outstanding list", str(listed)[:200])
status, body = sc.pay("708", bill, "BANK")
c.ok(status in (200, 201), "the payment is recorded", (status, message(body)))
if status in (200, 201):
    pay = data(body)
    num = pay.get("settlement_number") or pay.get("payment_number")
    c.ok(str(num).startswith("PY-"), "the number is a PY- number", num)
    listed = rows_of(a.get(f"{PAY}/outstanding?vendor_id={sc.vendor['id']}"))
    c.ok(not any(r.get("id") == bill["id"] or r.get("invoice_id") == bill["id"] for r in listed), "the bill is gone from the outstanding list", str(listed)[:200])
    c.eq(owing(a, sc.vendor["id"], bill["id"]), D(0), "the bill owes nothing")
    entries = journal(a, str(num))
    c.ok(len(entries) >= 1, "the payment has a journal entry")
    if entries:
        net = entry_net(a, entries[0])
        c.eq(net.get("ACCOUNTS_PAYABLE"), D(708), "Dr Accounts Payable 708.00")
        c.ok(sorted(net.values())[0] == D(-708), "Cr Bank 708.00", net)
c.done()
