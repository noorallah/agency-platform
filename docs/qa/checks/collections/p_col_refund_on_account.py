"""Probe (a), D-FIN-30: a refund comes off the receipt it was held on, and reversing it puts it back."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _col import *

c = Check("p_col_refund_on_account")
a = admin()
sc = Scene(a)
cust = sc.customer()
day = today().isoformat()
r = data(receipt(a, cust, "500.00")[1])
c.eq(D(r["unallocated_amount"]), D("500.00"), "a receipt on account holds 500.00 unapplied")


def unapplied() -> Decimal:
    """Return what the receipt still holds unapplied."""
    return D(must(a.get(f"{RC}/{r['id']}"), "receipt")["unallocated_amount"])


def refund(amount: str) -> tuple[int, Any]:
    """Refund an amount to the customer."""
    return a.post(RF, {"party_id": cust["id"], "settlement_date": day, "amount": amount, "method": "BANK"})


mark = journal_count(a)
st, body = refund("200.00")
c.eq(st, 201, "a 200.00 refund is recorded")
refund_row = data(body)
c.eq(unapplied(), D("300.00"), "the receipt now reads 300.00 unapplied")
c.eq(position(a, cust), (D("0"), D("300.00")), "the customer's advance agrees: 300.00")
c.eq(must(a.get(f"{CU}/{cust['id']}/account"), "account")["unapplied_advance"], "300.00", "so does the account view")
c.eq(journal_count(a), mark + 1, "one journal entry for the refund")
entry = entry_by_id(a, refund_row["journal_entry_id"])
c.eq(entry_net(a, entry), {"ACCOUNTS_RECEIVABLE": D("200.00"), "BANK": D("-200.00")}, "Dr receivable / Cr bank 200.00")
c.eq(refund("400.00")[0], 422, "refunding more than the 300.00 left is refused")
c.eq(unapplied(), D("300.00"), "the refusal moved nothing")
st, body = a.post(f"{RF}/{refund_row['id']}/reverse", {"reason": "check"})
c.eq(st, 200, "the refund is reversed")
c.eq(unapplied(), D("500.00"), "the receipt reads 500.00 again")
c.eq(position(a, cust), (D("0"), D("500.00")), "the customer's advance is 500.00 again")
c.eq(a.post(f"{RF}/{refund_row['id']}/reverse", {"reason": "twice"})[0], 422, "reversing it twice is refused")
c.eq(unapplied(), D("500.00"), "and moves nothing")
c.done()
