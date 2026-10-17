"""TC-COMM-002: approve posts the accrual journal; twice, or by the accruer, is refused."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _comm import *

c = Check("tc_comm_002")
who = actors()
a, approver = who["admin"], who["acct1"]
sc = Scene(a, stock="100")
sm, r, p, day = draft(a, sc)

# The accruer may not approve their own accrual (D-TER-4).
status, body = a.post(f"{PAYOUTS}/{p['id']}/approve", {})
c.ok(status == 403, "the accruer cannot approve", f"{status} {message(body)}")
c.eq(payout(a, p["id"])["status"], "DRAFT", "still DRAFT after the refusal")

status, body = approver.post(f"{PAYOUTS}/{p['id']}/approve", {})
c.eq(status, 200, f"another holder of COMMISSION_MANAGE approves ({message(body)})")
got = payout(a, p["id"])
c.eq(got["status"], "APPROVED", "status APPROVED")
c.ok(got["approved_by"] is not None and got["approved_at"] is not None, "approver and time recorded")
c.ok(got["approved_by"] != got["accrued_by"], "approver is not the accruer")
c.ok(got["payment_journal_entry_id"] is None, "no payment journal yet")
if c.ok(got["journal_entry_id"], "approval stored a journal entry id"):
    je = journal(a, got["journal_entry_id"])
    c.eq(je["status"], "POSTED", "the accrual journal is POSTED")
    c.eq(D(je["total_debit"]), D(got["payable_amount"]), "journal debit equals payable")
    c.eq(D(je["total_credit"]), D(got["payable_amount"]), "journal credit equals payable")
    c.eq(D(je["total_debit"]), Decimal("100.00"), "journal is the 100.00 earned")
    c.ok(je["reference_number"], "journal carries a reference", je["reference_number"])
    c.ok(len(je["lines"]) >= 2, "journal has a debit and a credit line", len(je["lines"]))

for key in ("acct1", "acct2", "admin"):
    status, body = who[key].post(f"{PAYOUTS}/{p['id']}/approve", {})
    c.ok(status in (400, 409, 422), f"approve again refused ({key})", f"{status} {message(body)}")
after = payout(a, p["id"])
c.eq(after["journal_entry_id"], got["journal_entry_id"], "no second journal after a repeat approve")
c.eq(after["status"], "APPROVED", "still APPROVED")
c.done()
