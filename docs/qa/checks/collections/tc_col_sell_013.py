"""TC-SELL-013: a receipt collects no TCS; an excess with nothing else owed is an advance."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _col import *

c = Check("tc_col_sell_013")
a = admin()
sc = Scene(a)
cust = sc.customer(tcs_applicable=True)
with counter(a):
    bill = sc.bill(cust, "4")  # 4 x 100 + 18% = 472.00
c.eq(D(bill["grand_total"]), D("472.00"), "the bill is 472.00")
st, body = receipt(a, cust, "236.00", [(bill, "236.00")])
c.eq(st, 201, "step 1: the first receipt is recorded")
r1 = data(body)
c.eq(D(r1["amount"]), D("236.00"), "the receipt is for exactly 236.00 (no TCS added)")
c.eq(D(r1["allocated_amount"]), D("236.00"), "all of it is set against the bill")
c.eq(D(r1["unallocated_amount"]), D("0"), "nothing left over")
c.eq(position(a, cust), (D("236.00"), D("0")), "outstanding 236.00, no advance")
c.eq(owing(a, cust, bill), D("236.00"), "the bill still owes 236.00")
st, body = receipt(a, cust, "336.00", [(bill, "236.00")])
c.eq(st, 201, "step 2: the second receipt is recorded")
r2 = data(body)
c.eq(D(r2["unallocated_amount"]), D("100.00"), "100.00 left over")
c.eq(position(a, cust), (D("0.00"), D("100.00")), "outstanding 0.00 and advance 100.00")
c.eq(owing(a, cust, bill), D("0"), "the bill drops out of the outstanding list")
for r in (r1, r2):
    e = entry_by_id(a, r["journal_entry_id"])
    c.ok(balanced(e), f"{r['settlement_number']}'s entry balances")
    c.eq(
        entry_net(a, e),
        {"BANK": D(r["amount"]), "ACCOUNTS_RECEIVABLE": -D(r["amount"])},
        f"{r['settlement_number']} is Dr Bank / Cr Receivables for the whole amount",
    )
    c.eq(len(journal(a, r["settlement_number"])), 1, f"one entry for {r['settlement_number']}")
c.eq(journal(a, f"TCS-{r1['settlement_number']}"), [], "no TCS-RC entry for the first receipt")
c.eq(journal(a, f"TCS-{r2['settlement_number']}"), [], "no TCS-RC entry for the second receipt")
c.done()
