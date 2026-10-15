"""TC-BUY-036: approve a bill and pay it in the same step."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _buy import *

c = Check("tc_buy_036")
a = admin()
sc = Scene(a)
vid = sc.vendor["id"]
order = sc.order()
sc.receive(order, "4")
r6 = sc.receive(order, "6")
bill = sc.bill(r6, approve=False)
c.eq(bill["status"], "DRAFT", "the bill is a draft")
done = a.post(f"{PI}/{bill['id']}/approve", {"payment": {"method": "CASH"}})
c.eq(done[0], 200, "approve with Paid now (Cash, amount blank)")
after = must(a.get(f"{PI}/{bill['id']}"), "bill")
c.eq(after["status"], "APPROVED", "the bill is APPROVED")
c.eq(owing(a, vid, bill["id"]), D(0), "Record Payment no longer lists the bill")
pays = rows_of(a.get(f"{PAY}?vendor_id={vid}&page_size=50"))
c.eq(len(pays), 1, "one payment for the supplier")
if pays:
    p = pays[0]
    c.ok(str(p["settlement_number"]).startswith("PY-"), "numbered PY-", p["settlement_number"])
    c.eq(D(p["amount"]), D(708), "of 708.00")
    c.eq(p["settlement_date"], bill["invoice_date"], "dated the bill's date")
    c.eq(p["method"], "CASH", "by cash")
    pj = journal(a, p["settlement_number"])
    c.ok(len(pj) >= 1, "the payment's journal exists")
    if pj:
        net = entry_net(a, pj[0])
        c.eq(net.get("ACCOUNTS_PAYABLE"), D(708), "Dr Trade Payables 708.00")
        c.ok(D(-708) in net.values(), "Cr Cash 708.00", net)
bj = journal(a, bill["invoice_number"])
c.ok(len(bj) >= 1, "the bill's journal exists")
if bj:
    net = entry_net(a, bj[0])
    c.eq([net.get(k) for k in ("GOODS_RECEIVED_NOT_INVOICED", "INPUT_TAX_CGST", "INPUT_TAX_SGST", "ACCOUNTS_PAYABLE")],
         [D(600), D(54), D(54), D(-708)], "Dr GRNI 600, Dr CGST 54, Dr SGST 54 / Cr Payables 708")
c.done()
