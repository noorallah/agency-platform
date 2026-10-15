"""TC-BUY-037: paying part now leaves the rest owing; more than the bill is refused."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _buy import *

c = Check("tc_buy_037")
a = admin()
sc = Scene(a)
vid = sc.vendor["id"]
order = sc.order()
sc.receive(order, "4")
r6 = sc.receive(order, "6")
bill = sc.bill(r6, approve=False)
over = a.post(f"{PI}/{bill['id']}/approve", {"payment": {"method": "BANK", "amount": "800"}})
c.refused(over, 422, "owes 708", "800 against a bill of 708")
c.eq(must(a.get(f"{PI}/{bill['id']}"), "bill")["status"], "DRAFT", "the bill is still a draft: the refusal took the approval back")
c.eq(len(rows_of(a.get(f"{PAY}?vendor_id={vid}&page_size=50"))), 0, "no payment was recorded")
part = a.post(f"{PI}/{bill['id']}/approve", {"payment": {"method": "BANK", "amount": "300", "instrument_reference": "NEFT-QA-0300"}})
c.eq(part[0], 200, "300 is accepted")
c.eq(must(a.get(f"{PI}/{bill['id']}"), "bill")["status"], "APPROVED", "the bill is approved")
pays = rows_of(a.get(f"{PAY}?vendor_id={vid}&page_size=50"))
c.eq([(D(p["amount"]), p["method"]) for p in pays], [(D(300), "BANK")], "a bank payment of 300.00")
c.eq(owing(a, vid, bill["id"]), D(408), "the bill owes 408.00")
if pays:
    pj = journal(a, pays[0]["settlement_number"])
    c.ok(len(pj) >= 1, "the payment has a journal")
    if pj:
        net = entry_net(a, pj[0])
        c.eq(net.get("ACCOUNTS_PAYABLE"), D(300), "Dr Trade Payables 300.00")
        c.ok(D(-300) in net.values(), "Cr Bank 300.00", net)
c.done()
