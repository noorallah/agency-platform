"""TC-COMM-004: an approved payout cannot be edited; status is never writable through update."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _comm import *

c = Check("tc_comm_004")
who = actors()
a, acct1 = who["admin"], who["acct1"]
sc = Scene(a, stock="100")
sm, r, p, day = draft(a, sc)

# Control: a draft takes notes and an adjustment with a reason.
status, body = a.put(f"{PAYOUTS}/{p['id']}", {"notes": "checked"})
c.eq(status, 200, f"a draft takes a note ({message(body)})")
status, body = a.put(f"{PAYOUTS}/{p['id']}", {"adjustment_amount": "10.00", "adjustment_reason": "bonus"})
c.eq(status, 200, f"a draft takes a reasoned adjustment ({message(body)})")
d = payout(a, p["id"])
c.eq(D(d["payable_amount"]), D(d["earned_amount"]) + Decimal("10.00"), "payable moves by the adjustment")

# An explicit status is not accepted.
for value in ("PAID", "APPROVED", "CANCELLED"):
    status, body = a.put(f"{PAYOUTS}/{p['id']}", {"status": value})
    c.ok(status == 422, f"status={value} in the update body is a 422", f"{status} {message(body)}")
c.eq(payout(a, p["id"])["status"], "DRAFT", "status still DRAFT")

c.eq(acct1.post(f"{PAYOUTS}/{p['id']}/approve", {})[0], 200, "approved by acct1")
approved = payout(a, p["id"])

for body_ in ({"notes": "after"}, {"adjustment_amount": "50.00", "adjustment_reason": "late"}):
    status, body = a.put(f"{PAYOUTS}/{p['id']}", body_)
    c.ok(status in (400, 409, 422), f"update of an APPROVED payout refused {list(body_)}", f"{status} {message(body)}")
status, body = a.put(f"{PAYOUTS}/{p['id']}", {"status": "PAID"})
c.ok(status in (400, 409, 422), "status in the body of an APPROVED payout refused", f"{status} {message(body)}")
now = payout(a, p["id"])
c.eq(now["status"], "APPROVED", "status still APPROVED")
c.eq(D(now["payable_amount"]), D(approved["payable_amount"]), "payable unchanged")
c.eq(now["notes"], approved["notes"], "notes unchanged")
c.eq(now["version"], approved["version"], "version unchanged by refused edits")
c.done()
