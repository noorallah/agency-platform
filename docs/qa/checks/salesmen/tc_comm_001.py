"""TC-COMM-001: accrue makes draft payouts, snapshots the amount, and holds a period once."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _comm import *

c = Check("tc_comm_001")
a = admin()
sc = Scene(a, stock="100")
sm, r, day = earner(a, sc, "10")

status, body = accrue(a, sm, day)
c.eq(status, 201, f"accrue answers 201 ({message(body)})")
rows = data(body) if status == 201 else []
if c.eq(len(rows), 1, "one payout for the one earner"):
    p = rows[0]
    c.eq(p["status"], "DRAFT", "a new payout is DRAFT")
    c.eq(p["salesman_id"], sm["id"], "payout is the salesman's")
    c.eq(p["period_start"], day.isoformat(), "period start kept")
    # 10 x 100 = 1,000 net; 10% of it.
    c.eq(D(p["earned_amount"]), Decimal("100.00"), "earned 10% of 1,000 net")
    c.eq(D(p["payable_amount"]), Decimal("100.00"), "payable equals earned with no adjustment")
    c.ok(p["journal_entry_id"] is None, "a draft has no journal yet", p["journal_entry_id"])
    c.ok(p["accrued_by"] is not None, "accrued_by recorded")

    # Snapshot: change the rate afterwards; the payout must not move.
    status, body = a.put(f"{COMM}/rules/{r['id']}", {"percentage": "25"})
    c.ok(status == 200, "rule rate can be changed", f"{status} {message(body)}")
    again = payout(a, p["id"])
    c.eq(D(again["earned_amount"]), Decimal("100.00"), "earned unchanged after the rate moved")
    c.eq(D(again["payable_amount"]), Decimal("100.00"), "payable unchanged after the rate moved")
    c.eq(D(again["measured_amount"]), D(p["measured_amount"]), "measured base unchanged")

    # One live payout per person per period.
    for what, s, e in (
        ("same period", day, day),
        ("period that overlaps at its start", day - timedelta(days=1), day),
        ("period that contains it", day - timedelta(days=3), day),
    ):
        status, body = accrue(a, sm, s, e)
        c.ok(status in (400, 409, 422), f"second accrue refused: {what}", f"{status} {message(body)}")
    live = [x for x in rows_of(a.get(f"{PAYOUTS}?salesman_id={sm['id']}&page_size=50"))
            if x["status"] != "CANCELLED" and x["salesman_id"] == sm["id"]]
    c.eq(len(live), 1, "still exactly one live payout for the person")
c.done()
