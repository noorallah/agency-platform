"""TC-COMM-003: paying needs COMMISSION_PAY; payment and reversal post under their own references."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _comm import *

c = Check("tc_comm_003")
who = actors()
a, acct1, acct2, mgr, smgr = who["admin"], who["acct1"], who["acct2"], who["mgr"], who["smgr"]
sc = Scene(a, stock="200")
PAY = {"paid_on": today().isoformat(), "method": "CASH"}

# --- A: MANAGE-only user approves, then cannot pay.
sm, r, A, day = draft(a, sc)
status, body = mgr.post(f"{PAYOUTS}/{A['id']}/approve", {})
c.eq(status, 200, f"COMMISSION_MANAGE alone may approve ({message(body)})")
status, body = mgr.post(f"{PAYOUTS}/{A['id']}/pay", PAY)
c.ok(status == 403, "COMMISSION_MANAGE alone is refused on pay (403)", f"{status} {message(body)}")
status, body = smgr.post(f"{PAYOUTS}/{A['id']}/pay", PAY)
c.ok(status == 403, "SALES_MANAGER is refused on pay (403)", f"{status} {message(body)}")
c.eq(payout(a, A["id"])["status"], "APPROVED", "still APPROVED after the refusals")

# A different COMMISSION_PAY holder than the approver pays.
status, body = acct2.post(f"{PAYOUTS}/{A['id']}/pay", PAY)
c.eq(status, 200, f"a COMMISSION_PAY holder who did not approve pays ({message(body)})")
paid = payout(a, A["id"])
c.eq(paid["status"], "PAID", "status PAID")
c.ok(paid["paid_by"] is not None and paid["paid_by"] != paid["approved_by"], "payer differs from approver")
c.eq(paid["paid_on"], today().isoformat(), "paid_on kept")
if c.ok(paid["payment_journal_entry_id"] and paid["journal_entry_id"], "both journals recorded"):
    c.ok(paid["payment_journal_entry_id"] != paid["journal_entry_id"], "payment posts a separate journal")
    accr = journal(a, paid["journal_entry_id"])
    pj = journal(a, paid["payment_journal_entry_id"])
    c.ok(pj["reference_number"] != accr["reference_number"], "payment reference differs from accrual's",
         (pj["reference_number"], accr["reference_number"]))
    c.ok(pj["reference_number"].endswith("-PAY"), "payment reference ends -PAY", pj["reference_number"])
    c.eq(pj["status"], "POSTED", "payment journal POSTED")
    c.eq(D(pj["total_debit"]), D(paid["payable_amount"]), "payment journal equals payable")
status, body = acct2.post(f"{PAYOUTS}/{A['id']}/pay", PAY)
c.ok(status in (400, 409, 422), "paying twice refused", f"{status} {message(body)}")

# --- B: the approver cannot pay; cancel posts a reversal under its own reference.
sm2, r2, B, day2 = draft(a, sc)
c.eq(acct1.post(f"{PAYOUTS}/{B['id']}/approve", {})[0], 200, "B approved by acct1")
status, body = acct1.post(f"{PAYOUTS}/{B['id']}/pay", PAY)
c.ok(status == 403, "the approver cannot pay their own approval (403)", f"{status} {message(body)}")
approved = payout(a, B["id"])
status, body = acct2.post(f"{PAYOUTS}/{B['id']}/cancel", {})
c.eq(status, 200, f"cancel of an approved payout ({message(body)})")
c.eq(payout(a, B["id"])["status"], "CANCELLED", "status CANCELLED")
if c.ok(approved["journal_entry_id"], "B had an accrual journal"):
    orig = journal(a, approved["journal_entry_id"])
    rev_ref = f"{orig['reference_number']}-REV"
    found = [e for e in rows_of(a.get(f"{JE}?search={rev_ref}&page_size=20"))
             if e["reference_number"] == rev_ref]
    if c.eq(len(found), 1, "a reversal journal exists under reference <accrual>-REV"):
        c.ok(found[0]["reference_number"] != orig["reference_number"], "reversal reference is distinct")
        c.eq(found[0].get("reversal_of_id"), orig["id"], "reversal points at the accrual")
        c.eq(D(found[0]["total_debit"]), D(orig["total_debit"]), "reversal is for the same amount")
# The period is free again once cancelled.
status, body = accrue(a, sm2, day2)
c.eq(status, 201, f"a cancelled payout frees the period ({message(body)})")
c.done()
