"""TC-INCENT-014: a commission period is a start date and a number of days."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sm import *

c = Check("tc_incent_014")
a = admin()
sc = Scene(a, stock="200")
D0 = today() - timedelta(days=45)
person = sc.salesman(f"Ten {sc.tag}")
rule(a, person["id"], D0, effective_to=(D0 + timedelta(days=29)).isoformat(),
     percentage="10", basis="INVOICED")
for offset in (4, 12, 20, 28):
    sell(sc, person["id"], "2", "100", D0 + timedelta(days=offset))
ACC = f"{COMM}/payouts/accrue"
sid = person["id"]

status, body = a.post(ACC, {"period_start": D0.isoformat(), "period_days": 10, "salesman_id": sid})
if c.eq(status, 201, f"10 days from D ({message(body)[:150]})"):
    p = data(body)[0]
    c.eq(p["period_end"], (D0 + timedelta(days=9)).isoformat(), "10 days end on D+9, the start day counted")
    c.eq(D(p["measured_amount"]), Decimal("236"), "the first payout measures 236.00")
    c.eq(D(p["payable_amount"]), Decimal("20.00"), "and owes 20.00 (10% of 200 before tax)")
    c.eq(p.get("accrued_on"), p["period_end"], "booked on its last day")

status, body = a.post(ACC, {"period_start": (D0 + timedelta(days=10)).isoformat(), "period_days": 17, "salesman_id": sid})
if c.eq(status, 201, f"17 days from D+10 ({message(body)[:150]})"):
    p = data(body)[0]
    c.eq(p["period_end"], (D0 + timedelta(days=26)).isoformat(), "17 days run to D+26")
    c.eq(D(p["measured_amount"]), Decimal("472"), "the second payout measures 472.00 (two bills)")
    c.eq(D(p["payable_amount"]), Decimal("40.00"), "and owes 40.00")
    report = report_row(a, sid, D0 + timedelta(days=10), D0 + timedelta(days=26))
    c.eq(D(report.get("invoiced_amount")), D(p["measured_amount"]), "it agrees with the Collected report for the same days")

status, body = a.post(ACC, {"period_start": (D0 + timedelta(days=9)).isoformat(), "period_days": 17, "salesman_id": sid})
c.ok(status in (409, 422) and "already covers part of that period" in message(body),
     "a period starting on D+9 is refused", f"{status} {message(body)[:200]}")
c.ok(D0.isoformat() in message(body) and (D0 + timedelta(days=9)).isoformat() in message(body),
     "and names the covered days D to D+9", message(body)[:200])

both = {"period_start": (D0 + timedelta(days=27)).isoformat(), "salesman_id": sid}
c.refused(a.post(ACC, {**both, "period_end": (D0 + timedelta(days=30)).isoformat(), "period_days": 4}),
          422, "Give either period_end or period_days", "both end and days")
c.refused(a.post(ACC, both), 422, "period_end or period_days", "neither end nor days")
for days in (0, 367):
    status, body = a.post(ACC, {**both, "period_days": days})
    c.eq(status, 422, f"{days} days is refused")
status, body = a.post(ACC, {"period_start": (today() - timedelta(days=3)).isoformat(), "period_days": 10, "salesman_id": sid})
c.ok(status in (409, 422) and "accrued" in message(body).lower(),
     "a period whose last day is today or later is refused, naming the first day it can be accrued", f"{status} {message(body)[:200]}")
c.done()
