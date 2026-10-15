"""Probe: a supplier payment against a bill lowers what is owed, posts Dr Payables / Cr Bank, and its reversal restores both."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _fin import *

c = Check("p_fin_payment")
a = admin()
viewer = admin("viewer")
bs = buy.Scene(a)
vid = bs.vendor["id"]
_, _, bill = bs.received_and_billed("10")  # 1,000.00 + 18% = 1,180.00
c.eq(D(bill["grand_total"]), D("1180.00"), "the bill is 1,180.00")
c.eq(buy.owing(a, vid, bill["id"]), D("1180.00"), "owed in full")
per = period_of(a)
t0 = tb(a, per)
bank0, ap0 = closing(t0, "1010"), closing(t0, "2100")

c.eq(viewer.post(PAY, {"party_id": vid, "settlement_date": today().isoformat(), "amount": "10", "method": "BANK", "allocations": []})[0], 403, "a Viewer cannot pay")
st, made = bs.pay("400.25", bill)
c.eq(st, 201, "the payment is recorded")
pay = data(made)
c.eq(buy.owing(a, vid, bill["id"]), D("779.75"), "the bill owes 779.75 after 400.25")
c.eq((D(pay["amount"]), D(pay["allocated_amount"]), D(pay["unallocated_amount"])), (D("400.25"), D("400.25"), D("0")), "all of it allocated")
entries = journal(a, pay["settlement_number"])
c.eq(len(entries), 1, "one journal entry for the payment")
entry = entry_by_id(a, entries[0]["id"])
c.ok(balanced(entry), "the entry balances")
c.eq(entry_net(a, entry), {"ACCOUNTS_PAYABLE": D("400.25"), "BANK": D("-400.25")}, "Dr Payables 400.25 / Cr Bank 400.25")
t1 = tb(a, per)
c.eq(closing(t1, "2100") - ap0, D("400.25"), "Trade Payables closing moved 400.25 toward zero (Dr)")
c.eq(closing(t1, "1010") - bank0, D("-400.25"), "Bank closing down 400.25")

over = bs.pay("800.00", bill)
c.eq(over[0], 422, "paying more than the 779.75 left against the bill is refused")
c.eq(buy.owing(a, vid, bill["id"]), D("779.75"), "the refusal changed nothing")

st, rev = a.post(f"{PAY}/{pay['id']}/reverse", {"reason": "check"})
c.eq(st, 200, "the payment reverses")
c.eq(buy.owing(a, vid, bill["id"]), D("1180.00"), "the bill owes in full again")
t2 = tb(a, per)
c.eq(closing(t2, "2100"), ap0, "Payables back to the figure before the payment")
c.eq(closing(t2, "1010"), bank0, "Bank back to the figure before the payment")
dr, cr = sums(t2)
c.eq(dr, cr, "trial balance still balances")
both = {e["reference_number"]: e for e in journal(a, pay["settlement_number"])}
c.eq(sorted(e["status"] for e in both.values()), ["POSTED", "REVERSED"], "the original is marked REVERSED and its mirror is POSTED")
c.eq(set(both), {pay["settlement_number"], pay["settlement_number"] + "-REV"}, "the mirror is the number plus -REV")
c.eq(a.post(f"{PAY}/{pay['id']}/reverse", {"reason": "again"})[0] in (409, 422), True, "reversing twice is refused")
c.done()
