"""TC-FIN-013: post-dated cheques: hold, deposit, clear, bounce (both sides)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from datetime import timedelta

from _col import *

c = Check("tc_col_fin_013")
a = admin()
viewer = admin("viewer")
sc = Scene(a)
cust = sc.customer()
with counter(a):
    b1 = sc.bill(cust, "10")  # 1,180.00
    b2 = sc.bill(cust, "10")
t = today()
ahead = (t + timedelta(days=7)).isoformat()


def new_cheque(date: str, amount: str = "1180.00") -> dict:
    """Take a cheque from the customer."""
    return must(
        a.post(
            f"{PDC}/received",
            {
                "party_id": cust["id"], "cheque_number": suffix(6), "cheque_date": date,
                "amount": amount, "received_on": t.isoformat(), "drawn_on_bank": "HDFC",
            },
        ),
        "cheque",
    )


c.eq(
    viewer.post(f"{PDC}/received", {"party_id": cust["id"], "cheque_number": "V1", "cheque_date": ahead, "amount": "10", "received_on": t.isoformat()})[0],
    403, "a Viewer cannot take a cheque",
)
before_j = journal_count(a)
held = new_cheque(ahead)
c.eq(held["status"], "HELD", "a cheque dated ahead is held")
c.eq(journal_count(a), before_j, "holding posts nothing")
c.eq(position(a, cust), (D("2360.00"), D("0")), "the customer still owes both bills")
dep = {"deposited_on": t.isoformat(), "allocations": [{"invoice_id": b1["id"], "amount": "1180.00"}]}
c.refused(a.post(f"{PDC}/received/{held['id']}/deposit", dep), 422, "will not take it before", "deposit before the cheque's date is refused")
c.eq(must(a.get(f"{PDC}/received/{held['id']}"), "read")["status"], "HELD", "the refusal left it held")
due = [r["id"] for r in all_rows(a, f"{PDC}/received?due_on={t.isoformat()}&party_id={cust['id']}")]
c.ok(held["id"] not in due, "filtered to due today, the cheque dated ahead is not listed")
# a cheque dated today: deposit -> receipt, clear posts nothing
first = new_cheque(t.isoformat())
due = [r["id"] for r in all_rows(a, f"{PDC}/received?due_on={t.isoformat()}&party_id={cust['id']}")]
c.ok(first["id"] in due, "the cheque dated today is listed as due today")
done = must(a.post(f"{PDC}/received/{first['id']}/deposit", dep), "deposit")
c.eq(done["status"], "DEPOSITED", "deposited")
settlement = must(a.get(f"{RC}/{done['settlement_id']}"), "settlement")
c.eq(settlement["payment_mode"], "CHEQUE", "the receipt's mode is Cheque")
c.eq(settlement["instrument_reference"], first["cheque_number"], "carrying the cheque number")
c.eq(D(settlement["amount"]), D("1180.00"), "for the cheque's amount")
c.eq(position(a, cust), (D("1180.00"), D("0")), "the first bill is paid")
c.refused(a.post(f"{PDC}/received/{first['id']}/deposit", {"deposited_on": t.isoformat(), "allocations": []}), 422, "cannot be banked", "a cheque cannot be deposited twice")
mark = journal_count(a)
cleared = must(a.post(f"{PDC}/received/{first['id']}/clear", {"cleared_on": t.isoformat()}), "clear")
c.eq(cleared["status"], "CLEARED", "cleared")
c.eq(journal_count(a), mark, "clearing posts nothing")
c.eq(position(a, cust), (D("1180.00"), D("0")), "and moves no balance")
c.refused(a.post(f"{PDC}/received/{first['id']}/bounce", {"bounced_on": t.isoformat(), "reason": "late"}), 422, "cannot be returned", "a cleared cheque cannot bounce")
# a second cheque: deposit then bounce with charges 100
second = new_cheque(t.isoformat())
dep2 = {"deposited_on": t.isoformat(), "allocations": [{"invoice_id": b2["id"], "amount": "1180.00"}]}
done2 = must(a.post(f"{PDC}/received/{second['id']}/deposit", dep2), "deposit 2")
c.eq(position(a, cust), (D("0"), D("0")), "both bills paid")
bounced = must(
    a.post(
        f"{PDC}/received/{second['id']}/bounce",
        {"bounced_on": t.isoformat(), "reason": "no funds", "bank_charges_amount": "100", "customer_charge_amount": "100"},
    ),
    "bounce",
)
c.eq(bounced["status"], "BOUNCED", "bounced")
c.eq(must(a.get(f"{RC}/{done2['settlement_id']}"), "read")["status"], "REVERSED", "the settlement is reversed")
c.eq(position(a, cust), (D("1280.00"), D("0")), "the customer owes the bill again plus the 100.00 charge")
c.eq(owing(a, cust, b2), D("1180.00"), "the second bill owes in full again")
charges = entry_by_id(a, bounced["charges_journal_entry_id"])
c.ok(balanced(charges), "the charges entry balances")
c.eq(
    entry_net(a, charges),
    {"BANK_CHARGES": D("100"), "BANK": D("-100"), "ACCOUNTS_RECEIVABLE": D("100"), "CHEQUE_RETURN_CHARGES": D("-100")},
    "Dr bank charges / Cr bank, and Dr receivable / Cr cheque-return charges",
)
c.refused(a.post(f"{PDC}/received/{second['id']}/bounce", {"bounced_on": t.isoformat(), "reason": "again"}), 422, "cannot be returned", "a bounced cheque cannot bounce again")
# a third: cancel while held
third = new_cheque(ahead, "50.00")
c.eq(must(a.post(f"{PDC}/received/{third['id']}/cancel", {"reason": "wrong"}), "cancel")["status"], "CANCELLED", "a held cheque can be cancelled")
c.refused(a.post(f"{PDC}/received/{third['id']}/deposit", {"deposited_on": t.isoformat(), "allocations": []}), 422, "cancelled", "a cancelled cheque cannot be deposited")
# the issued side
vendor = must(a.post("/api/v1/vendors", {"code": f"CV{sc.tag}", "name": f"Collections vendor {sc.tag}"}), "vendor")
mark = journal_count(a)
issued = must(
    a.post(f"{PDC}/issued", {"party_id": vendor["id"], "cheque_number": suffix(6), "cheque_date": t.isoformat(), "amount": "300.00", "received_on": t.isoformat()}),
    "issued cheque",
)
c.eq(issued["status"], "HELD", "an issued cheque is held")
c.eq(journal_count(a), mark, "holding it posts nothing")
paid = must(a.post(f"{PDC}/issued/{issued['id']}/deposit", {"deposited_on": t.isoformat(), "allocations": []}), "issued deposit")
c.eq(paid["status"], "DEPOSITED", "presented")
pay = must(a.get(f"/api/v1/payments/{paid['settlement_id']}"), "payment")
c.eq(pay["payment_mode"], "CHEQUE", "the payment's mode is Cheque")
c.eq(D(pay["amount"]), D("300.00"), "for 300.00")
c.eq(pay["direction"], "PAYMENT", "and it is a payment")
c.eq(viewer.post(f"{PDC}/issued", {"party_id": vendor["id"], "cheque_number": "V2", "cheque_date": ahead, "amount": "1", "received_on": t.isoformat()})[0], 403, "a Viewer cannot issue one")
c.done()
