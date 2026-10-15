"""Probe: odd paise, TDS, rounding and bank charges on a receipt keep the journal exact and reverse cleanly."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _col import *

c = Check("p_col_paise_and_deductions")
a = admin()
sc = Scene(a, price="33.33")
cust = sc.customer()
with counter(a):
    small = sc.bill(cust, "3")   # 99.99 + 18% = 117.9882, carried to the ledger as 117.99
    large = sc.bill(cust, "7")   # 233.31 + 18% = 275.3058, carried as 275.31
c.eq(owing(a, cust, small), D("117.99"), "an odd-paise bill owes its ledger value, 117.99")
c.eq(owing(a, cust, large), D("275.31"), "and the second 275.31")
c.eq(position(a, cust), (D("393.30"), D("0")), "the customer owes the exact sum, 393.30")
st, body = receipt(a, cust, "117.99", [(small, "117.99")])
c.eq(st, 201, "paying exactly what the bill owes is accepted")
first = data(body)
c.eq(owing(a, cust, small), D("0"), "and closes it")
entry = entry_by_id(a, first["journal_entry_id"])
c.ok(balanced(entry), "the entry balances")
c.eq(entry_net(a, entry), {"BANK": D("117.99"), "ACCOUNTS_RECEIVABLE": D("-117.99")}, "Dr bank / Cr receivable 117.99")
# deductions: amount 275.31 settles the bill; cash is what is left after the three
st, body = receipt(a, cust, "275.31", [(large, "275.31")], tds_amount="10.00", tds_section="194Q", rounding_amount="0.50", bank_charges_amount="1.25")
c.eq(st, 201, "a receipt with TDS, rounding and bank charges is accepted")
second = data(body)
c.eq(D(second["cash_amount"]), D("263.56"), "cash received is 275.31 less 10.00, 0.50 and 1.25 = 263.56")
c.eq(owing(a, cust, large), D("0"), "the bill is closed for the whole 275.31")
entry = entry_by_id(a, second["journal_entry_id"])
c.ok(balanced(entry), "its entry balances")
c.eq(
    entry_net(a, entry),
    {"BANK": D("263.56"), "TDS_RECEIVABLE": D("10.00"), "ROUNDING": D("0.50"), "BANK_CHARGES": D("1.25"), "ACCOUNTS_RECEIVABLE": D("-275.31")},
    "Dr bank 263.56, TDS 10.00, rounding 0.50, bank charges 1.25 / Cr receivable 275.31",
)
c.eq(position(a, cust), (D("0"), D("0")), "the customer owes nothing")
c.eq(a.post(f"{RC}/{second['id']}/reverse", {"reason": "check"})[0], 200, "the second receipt is reversed")
c.eq((owing(a, cust, large), position(a, cust)), (D("275.31"), (D("275.31"), D("0"))), "the bill owes its 275.31 again, exactly")
back = entry_by_id(a, must(a.get(f"{RC}/{second['id']}"), "read")["reversal_journal_entry_id"])
c.ok(balanced(back), "the reversal entry balances")
c.eq(entry_net(a, back), {k: -v for k, v in entry_net(a, entry).items()}, "and is the exact mirror of the original")
c.done()
