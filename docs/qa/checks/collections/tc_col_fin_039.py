"""TC-FIN-039: a cheque written to any account, dated today or ahead (server half)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from datetime import timedelta

from _col import *

c = Check("tc_col_fin_039")
a = admin()
sc = Scene(a)
t = today()
accounts = must(a.get(f"{PDC}/issued/accounts"), "cheque accounts")
bank = accounts["bank_accounts"][0]["id"]
rent = next(x for x in accounts["expense_accounts"] if x["name"] == "Rent")["id"]
capital = next(x for x in accounts["other_accounts"] if x["name"] == "Capital")["id"]
W = f"{PDC}/issued/write"


def write(**body: object) -> tuple[int, Any]:
    """Write a cheque on the firm's bank account."""
    return a.post(W, {"bank_account_id": bank, "cheque_number": suffix(6), "cheque_date": t.isoformat(), **body})


vendor = must(a.post("/api/v1/vendors", {"code": f"WV{sc.tag}", "name": f"Cheque supplier {sc.tag}"}), "vendor")
bank0 = account_balance(a, "Bank")
# 1
st, body = write(account_id=rent, amount="1250.00")
c.eq(st, 201, "step 1: a cheque to an expense account dated today is written")
exp_cheque = data(body)
c.eq(exp_cheque["paid_to_kind"], "EXPENSE", "it pays an expense")
c.ok(exp_cheque["expense_number"], "recorded as an expense number", exp_cheque.get("expense_number"))
c.eq(account_balance(a, "Bank") - bank0, D("-1250.00"), "the bank is down by 1,250.00")
# 2, 3
status, raw = a.raw(f"{PDC}/issued/{exp_cheque['id']}/print")
c.eq((status, raw[:4]), (200, b"%PDF"), "step 2: the cheque prints")
status, raw = a.raw(f"/api/v1/expenses/{exp_cheque['expense_id']}/cheque")
c.eq((status, raw[:4]), (200, b"%PDF"), "step 3: the same cheque prints from the expense")
# 4
mark, before_j = account_balance(a, "Bank"), journal_count(a)
st, body = write(supplier_id=vendor["id"], payee_name="Typed Name", amount="4000.00", cheque_date=(t + timedelta(days=30)).isoformat())
c.eq(st, 201, "step 4: a cheque dated a month ahead is written")
ahead = data(body)
c.eq(ahead["status"], "HELD", "it is Held")
c.eq(ahead["payee_name"], "Typed Name", "the name typed is kept")
c.eq((ahead["expense_id"], ahead["settlement_id"], ahead["journal_entry_id"]), (None, None, None), "nothing is recorded against it")
c.eq(account_balance(a, "Bank"), mark, "the bank has not moved")
c.eq(journal_count(a), before_j, "no journal entry was posted")
status, raw = a.raw(f"{PDC}/issued/{ahead['id']}/print")
c.eq((status, raw[:4]), (200, b"%PDF"), "Print cheque prints it now")
# 5
c.refused(
    a.post(f"{PDC}/issued/{ahead['id']}/deposit", {"deposited_on": t.isoformat(), "allocations": []}),
    422, "will not take it before", "step 5: presenting before its date is refused",
)
c.eq(must(a.get(f"{PDC}/issued/{ahead['id']}"), "read")["status"], "HELD", "it is still held")
# 6
c.refused(write(account_id=rent, amount="10.00", cheque_number=exp_cheque["cheque_number"]), 422, exp_cheque["cheque_number"], "step 6: the same number on the same bank is refused naming the number")
# 7
cust = sc.customer()
c.eq(receipt(a, cust, "500.00")[0], 201, "set-up: the customer holds 500.00 on account")
st, body = write(customer_id=cust["id"], amount="500.00")
c.eq(st, 201, "step 7: a cheque to the customer is written")
refund = data(body)
c.ok(str(refund["settlement_number"]).startswith("RF-"), "recorded as a refund", refund.get("settlement_number"))
c.eq(position(a, cust), (D("0"), D("0")), "the customer holds 0.00")
status, raw = a.raw(f"/api/v1/refunds/{refund['settlement_id']}/cheque")
c.eq((status, raw[:4]), (200, b"%PDF"), "the refund prints as a cheque")
# 8
cap0, bank1 = account_balance(a, "Capital"), account_balance(a, "Bank")
st, body = write(account_id=capital, amount="10000.00")
c.eq(st, 201, "step 8: a cheque to a ledger account no document keeps")
voucher = data(body)
c.eq(voucher["paid_to_kind"], "ACCOUNT", "it pays an account")
c.ok(voucher["journal_entry_id"], "recorded as a payment voucher", voucher.get("journal_entry_id"))
entry = entry_by_id(a, voucher["journal_entry_id"])
c.ok(balanced(entry), "its entry balances")
c.eq(account_balance(a, "Capital") - cap0, D("-10000.00"), "the ledger account is debited 10,000.00")
c.eq(account_balance(a, "Bank") - bank1, D("-10000.00"), "and the bank credited 10,000.00")
# 9
st, body = write(supplier_id=vendor["id"], amount="900.00", cheque_date=(t + timedelta(days=10)).isoformat())
held = data(body)
c.eq(a.post(f"{PDC}/issued/{held['id']}/cancel", {"reason": "wrong payee"})[0], 200, "step 9: a held cheque is cancelled with a reason")
c.eq(must(a.get(f"{PDC}/issued/{held['id']}"), "read")["status"], "CANCELLED", "it is Cancelled")
status, raw = a.raw(f"{PDC}/issued/{held['id']}/print")
c.eq(status, 422, "and Print cheque is refused for it")
# 10
before = account_balance(a, "Bank")
st, body = a.post(f"{PDC}/issued/{exp_cheque['id']}/bounce", {"bounced_on": t.isoformat(), "reason": "stopped"})
c.eq(st, 200, "step 10: the cheque of step 1 is returned")
c.eq(data(body)["status"], "BOUNCED", "it is Bounced")
c.eq(must(a.get(f"/api/v1/expenses/{exp_cheque['expense_id']}"), "expense")["status"], "CANCELLED", "the expense it became is cancelled")
c.eq(account_balance(a, "Bank") - before, D("1250.00"), "and the bank has the 1,250.00 back")
c.done()
