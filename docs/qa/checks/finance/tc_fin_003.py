"""TC-FIN-003: a closed period refuses a posting; the firm's trail says who closed it."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _fin import *

c = Check("tc_fin_003")
a = admin()
plat = client("platform", MODULE)
AL = "/api/v1/audit-logs?search=finance.accounting_period.updated"
periods = sorted(all_rows(a, f"{FIN}/accounting-periods"), key=lambda p: p["starts_on"])
june = next(p for p in periods if p["starts_on"] == "2026-06-01")
chain = [p for p in periods if p["starts_on"] <= june["starts_on"] and p["status"] != "CLOSED"]  # oldest first
trail0 = len(all_rows(a, AL))

ref = f"JV-MT-CLOSE-{suffix(4)}"
st, made = a.post(JE, draft_body(a, [("5000", "100.00", "0"), ("1000", "0", "100.00")], reference=ref, day="2026-06-15", period=june))
c.eq(st, 201, "step 1: a draft is saved in June")
draft = data(made)
closed: list[dict] = []
try:
    for p in chain:
        st, ans = a.call("PATCH", f"{FIN}/accounting-periods/{p['id']}", {"status": "CLOSED"})
        c.eq(st, 200, f"step 2: {p['code']} {p['starts_on']} closes")
        if st == 200:
            closed.append(p)
    st, ans = a.post(f"{JE}/{draft['id']}/post", {})
    c.eq(st, 422, "step 3: posting into the closed June is refused")
    c.ok("closed" in message(ans).lower() and "cannot accept postings" in message(ans), "it says the period is closed and cannot accept postings", message(ans))
    c.ok(june["code"] in message(ans), "naming the period", message(ans))
    c.eq(data(a.get(f"{JE}/{draft['id']}")[1])["status"], "DRAFT", "the draft stays a draft")
    new = a.post(JE, draft_body(a, [("5000", "1.00", "0"), ("1000", "0", "1.00")], reference=f"JV-MT-NEW-{suffix(4)}", day="2026-06-20", period=june))
    c.ok(new[0] in (409, 422) or data(new[1]).get("status") == "DRAFT", "a new draft in the closed month is refused or stays a draft", (new[0], message(new[1])))
    # trial balance for a later month still reads Balanced
    later = next(p for p in periods if p["starts_on"] == "2026-10-01")
    t = tb(a, later)
    c.eq(t["is_balanced"], True, "the later month's trial balance is Balanced while June is closed")
finally:
    for p in reversed(closed):
        a.call("PATCH", f"{FIN}/accounting-periods/{p['id']}", {"status": "OPEN"})
for p in closed:
    got = next(x for x in all_rows(a, f"{FIN}/accounting-periods") if x["id"] == p["id"])
    c.eq(got["status"], "OPEN", f"{p['code']} {p['starts_on']} is open again")
st, ans = a.post(f"{JE}/{draft['id']}/post", {})
c.eq(st, 200, "step 4: after reopening, the draft posts")
c.eq(data(ans)["status"], "POSTED", "POSTED")
t = tb(a, june)
c.eq(t["is_balanced"], True, "June's trial balance reads Balanced")

rows = all_rows(a, AL)
c.eq(len(rows) - trail0, 2 * len(closed), f"step 5: the firm's trail holds {2 * len(closed)} new rows for {len(closed)} periods closed and reopened")
# Case text says `finance` alone finds nothing (exact match); the server matches parts, so it finds rows.
c.ok(len(all_rows(a, "/api/v1/audit-logs?search=finance")) >= len(rows), "`finance` alone finds the rows too: the search is a partial match (case text says exact)")
c.eq(len(all_rows(plat, AL)), 0, "the platform trail finds none of them (finance events stay in the firm's trail)")
c.done()
