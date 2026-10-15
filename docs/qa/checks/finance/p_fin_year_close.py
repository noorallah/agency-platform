"""Probe: a year closes only when every period is closed and no draft is dated in it; a closed year takes no posting; reopening needs its own permission and a reason, which the trail keeps."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _fin import *

c = Check("p_fin_year_close")
a = admin()
accountant = admin("accountant")
viewer = admin("viewer")

# A year older than every period the firm holds, so closing its periods is not
# held up by the live year's open months (periods close oldest first, firm-wide).
oldest = min(int(p["starts_on"][:4]) for p in all_rows(a, f"{FIN}/accounting-periods"))
y = oldest - 1
fy = must(a.post(f"{FIN}/financial-years", {"code": f"FY{y}", "name": f"Check year {y}", "starts_on": f"{y}-04-01", "ends_on": f"{y + 1}-03-31"}), "year")


def period(n: int, name: str, start: str, end: str) -> dict:
    """Make one monthly period of the check year."""
    return must(a.post(f"{FIN}/accounting-periods", {"financial_year_id": fy["id"], "period_number": n, "code": f"P0{n}", "name": name, "starts_on": start, "ends_on": end}), name)


p1 = period(1, "April", f"{y}-04-01", f"{y}-04-30")
p2 = period(2, "May", f"{y}-05-01", f"{y}-05-31")
YC = f"{FIN}/financial-years/{fy['id']}"
CLOSE = lambda: a.post(f"{YC}/close", {})  # noqa: E731

c.eq(accountant.post(f"{YC}/close", {})[0], 403, "an Accountant (no FINANCIAL_YEAR_CLOSE) cannot close a year")
c.eq(viewer.post(f"{YC}/close", {})[0], 403, "a Viewer cannot close a year")
c.refused(CLOSE(), 422, "of its periods are open", "close refused while both periods are open")

# a period in the middle of the year
draft = must(a.post(JE, draft_body(a, [("5000", "12.50", "0"), ("1000", "0", "12.50")], day=f"{y}-05-10", period=p2)), "draft")
c.eq(draft["status"], "DRAFT", "a draft is dated in May of the check year")
c.eq(a.call("PATCH", f"{FIN}/accounting-periods/{p2['id']}", {"status": "CLOSED"})[0], 422, "May cannot close before April")
c.eq(a.call("PATCH", f"{FIN}/accounting-periods/{p1['id']}", {"status": "CLOSED"})[0], 200, "April closes")
c.refused(CLOSE(), 422, "open", "close still refused while May is open")
c.eq(a.call("PATCH", f"{FIN}/accounting-periods/{p2['id']}", {"status": "CLOSED"})[0], 200, "May closes even with a draft inside (a warning, not a refusal)")
st, body = CLOSE()
c.eq(st, 422, "close refused while a draft journal is dated in the year")
c.ok(draft["reference_number"] in message(body) or "draft" in message(body).lower(), "the refusal names the draft", message(body))
c.eq(next(x for x in rows_of(a.get(f"{FIN}/financial-years")) if x["id"] == fy["id"])["is_locked"], False, "the year is not locked by a refused close")

# remove the draft: only a draft dated in a closed period; deletion or rejection are the ways out
gone = a.delete(f"{JE}/{draft['id']}")
if gone[0] != 204:
    gone = a.post(f"{JE}/{draft['id']}/reject", {"reason": "clearing the year"})
c.ok(gone[0] in (200, 204), "the draft can be removed to unblock the close", (gone[0], message(gone[1])))
st, body = CLOSE()
c.eq(st, 200, "the year closes once periods are closed and no draft remains")
closed = data(body)
c.eq(closed["is_locked"], True, "it reads is_locked")

# posting into the closed year
d2 = a.post(JE, draft_body(a, [("5000", "3.00", "0"), ("1000", "0", "3.00")], day=f"{y}-04-12", period=p1))
c.ok(d2[0] in (409, 422), "a draft dated in the closed year is refused", (d2[0], message(d2[1])))
c.ok(not rows_of(a.get(f"{JE}?search=JV-MJ-&accounting_period_id={p1['id']}")), "and nothing was written into the closed period")
c.eq(a.call("PATCH", f"{FIN}/accounting-periods/{p1['id']}", {"status": "OPEN"})[0] in (409, 422), True, "a period of a closed year cannot be reopened one by one")

# reopen: its own permission and a reason
RO = f"{YC}/reopen"
c.eq(accountant.post(RO, {"reason": "audit adjustment"})[0], 403, "an Accountant cannot reopen (no FINANCIAL_YEAR_REOPEN)")
c.eq(viewer.post(RO, {"reason": "audit adjustment"})[0], 403, "a Viewer cannot reopen")
c.eq(a.post(RO, {})[0], 422, "reopen without a reason is refused")
c.eq(a.post(RO, {"reason": "   "})[0], 422, "reopen with a blank reason is refused")
c.eq(next(x for x in rows_of(a.get(f"{FIN}/financial-years")) if x["id"] == fy["id"])["is_locked"], True, "refused reopens leave it closed")
reason = f"auditor asked for a late adjustment {suffix(5)}"
st, body = a.post(RO, {"reason": reason})
c.eq(st, 200, "the firm administrator reopens it with a reason")
c.eq(data(body)["is_locked"], False, "the year is unlocked")

# the trail keeps the reason
found = False
for row in all_rows(a, "/api/v1/audit-logs?search=financial_year"):
    if reason in str(row):
        found = True
        break
if not found:
    for row in all_rows(a, f"/api/v1/audit-logs?search={reason.split()[-1]}"):
        found = True
c.ok(found, "the reopen reason is in the firm's audit trail")
c.done()
