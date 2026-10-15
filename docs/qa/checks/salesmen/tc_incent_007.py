"""TC-INCENT-007: payouts accrue, approve, pay and cancel; an overlapping accrual is refused."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sm import *

c = Check("tc_incent_007")
a = admin()
# Approval is a second person's: a second Firm admin approves and pays.
held = state()
email_b = f"{held['suffix']}.smadminb@fixtures.local"
ensure_user(admin("platform"), email_b, "Salesman check second admin", held["firm_id"], "FIRM_ADMIN")
b = sign_in(email_b, firm_id=held["firm_id"])
sc = Scene(a, stock="300")
D0 = today() - timedelta(days=40)      # the period must be over before it accrues
asha = sc.salesman(f"Asha {sc.tag}")
bala = sc.salesman(f"Bala {sc.tag}")
start = (D0 - timedelta(days=3))
rule(a, asha["id"], start, percentage="10")
rule(a, bala["id"], start, percentage="2")
sell(sc, asha["id"], "20", "100", D0 + timedelta(days=2), collect=True)
sell(sc, bala["id"], "30", "100", D0 + timedelta(days=3), collect=True)
period = {"period_start": D0.isoformat(), "period_days": 20}

got = {}
for name, person in (("Asha", asha), ("Bala", bala)):
    status, body = a.post(f"{COMM}/payouts/accrue", {**period, "salesman_id": person["id"]})
    if c.eq(status, 201, f"{name} accrues ({message(body)[:150]})"):
        row = data(body)[0]
        got[name] = row
        c.eq(row["status"], "DRAFT", f"{name}'s payout is a DRAFT")
c.eq(D(got.get("Asha", {}).get("payable_amount")), Decimal("200.00"), "Asha owed 10% of 2,000")
c.eq(D(got.get("Bala", {}).get("payable_amount")), Decimal("60.00"), "Bala owed 2% of 3,000")

if got.get("Bala") and got.get("Asha"):
    pid = got["Bala"]["id"]
    c.refused(a.post(f"{COMM}/payouts/{pid}/pay", {"paid_on": today().isoformat(), "method": "CASH"}),
              422, "Only an approved payout can be paid. Approve it first", "paying a draft")
    status, body = b.post(f"{COMM}/payouts/{pid}/approve", {})
    c.eq(status, 200, f"approve ({message(body)[:150]})")
    approved = data(body) if status == 200 else {}
    c.eq(approved.get("status"), "APPROVED", "approved")
    c.ok(bool(approved.get("journal_entry_id")), "approving puts the cost and the debt on the ledger", approved)
    status, body = a.post(f"{COMM}/payouts/{pid}/pay", {"paid_on": today().isoformat(), "method": "CASH"})
    c.eq(status, 200, f"pay ({message(body)[:150]})")
    paid = data(body) if status == 200 else {}
    c.eq(paid.get("status"), "PAID", "paid")
    c.ok(bool(paid.get("payment_journal_entry_id")), "paying posts its own journal", paid)
    c.ok(paid.get("payment_journal_entry_id") != paid.get("journal_entry_id"), "a distinct journal from the accrual")

    status, body = a.post(f"{COMM}/payouts/{got['Asha']['id']}/cancel", {})
    c.eq(status, 200, f"cancel Asha's draft ({message(body)[:150]})")
    c.eq(data(body).get("status") if status == 200 else None, "CANCELLED", "cancelled")
    c.ok(not data(body).get("journal_entry_id") if status == 200 else False, "nothing was posted for a draft")

    status, body = a.post(f"{COMM}/payouts/accrue", {**period, "salesman_id": bala["id"]})
    c.ok(status in (409, 422) and "already covers part of that period" in message(body),
         "Bala's period again is refused", f"{status} {message(body)[:150]}")
    status, body = a.post(f"{COMM}/payouts/accrue", {**period, "salesman_id": asha["id"]})
    c.eq(status, 201, f"Asha's period can accrue again ({message(body)[:150]})")
c.done()
