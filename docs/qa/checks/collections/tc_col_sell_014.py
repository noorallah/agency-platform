"""TC-SELL-014: applying an advance posts nothing; reversing a receipt puts everything back."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _col import *

c = Check("tc_col_sell_014")
a = admin()
sc = Scene(a)
cust = sc.customer()
with counter(a):
    bill_a = sc.bill(cust, "4")  # 472.00
    r1 = data(receipt(a, cust, "236.00", [(bill_a, "236.00")])[1])
    r2 = data(receipt(a, cust, "336.00", [(bill_a, "236.00")])[1])
    bill_b = sc.bill(cust, "7")  # 826.00
c.eq(D(bill_b["grand_total"]), D("826.00"), "the second bill is 826.00")
c.eq(position(a, cust), (D("826.00"), D("100.00")), "set-up: owes 826.00, holds 100.00")
before = journal_count(a)
st, body = a.post(f"{RC}/{r2['id']}/allocate", {"invoice_id": bill_b["id"], "amount": "95"})
c.eq(st, 200, "step 1: applying 95 of the advance is accepted")
c.eq(journal_count(a), before, "applying an advance writes no journal entry")
c.eq(position(a, cust), (D("731.00"), D("5.00")), "outstanding 731.00 and advance 5.00")
c.eq(D(must(a.get(f"{RC}/{r2['id']}"), "read")["unallocated_amount"]), D("5.00"), "the receipt has 5.00 unapplied")
c.refused(
    a.post(f"{RC}/{r2['id']}/allocate", {"invoice_id": bill_b["id"], "amount": "10"}),
    422, "5.00", "applying 10 more is refused naming what is left",
)
c.eq(position(a, cust), (D("731.00"), D("5.00")), "the refusal moved nothing")
st, body = a.post(f"{RC}/{r1['id']}/reverse", {"reason": "check"})
c.eq(st, 200, "step 2: the 236.00 receipt is reversed")
got = data(body)
c.eq(got["status"], "REVERSED", "the receipt reads reversed")
c.eq(position(a, cust), (D("967.00"), D("5.00")), "outstanding rises by 236.00 to 967.00; advance stays 5.00")
c.ok(journal(a, f"{r1['settlement_number']}-REV"), "a -REV journal entry exists")
c.refused(a.post(f"{RC}/{r1['id']}/reverse", {"reason": "again"}), 422, "already been reversed", "reversing twice is refused")
c.eq(position(a, cust), (D("967.00"), D("5.00")), "the second reversal moved nothing")
c.done()
