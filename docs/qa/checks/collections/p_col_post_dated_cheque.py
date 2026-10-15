"""Probe (c): a post-dated cheque posts nothing until its date, and cannot be posted twice (even together)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from _col import *

c = Check("p_col_post_dated_cheque")
a = admin()
sc = Scene(a)
cust = sc.customer()
with counter(a):
    bill = sc.bill(cust, "10")  # 1,180.00
t = today()
ahead = (t + timedelta(days=15)).isoformat()


def take(date: str) -> dict:
    """Take a 1,180.00 cheque from the customer."""
    return must(a.post(f"{PDC}/received", {"party_id": cust["id"], "cheque_number": suffix(7), "cheque_date": date, "amount": "1180.00", "received_on": t.isoformat()}), "cheque")


def deposit_body() -> dict:
    """Return a deposit that settles the bill."""
    return {"deposited_on": t.isoformat(), "allocations": [{"invoice_id": bill["id"], "amount": "1180.00"}]}


mark = journal_count(a)
held = take(ahead)
c.eq((journal_count(a), position(a, cust), owing(a, cust, bill)), (mark, (D("1180.00"), D("0")), D("1180.00")), "a cheque written ahead moves no journal and no balance")
c.eq(a.post(f"{PDC}/received/{held['id']}/deposit", deposit_body())[0], 422, "it cannot be deposited today")
c.eq(a.post(f"{PDC}/received/{held['id']}/clear", {"cleared_on": t.isoformat()})[0], 422, "nor cleared while held")
c.eq(a.post(f"{PDC}/received/{held['id']}/bounce", {"bounced_on": t.isoformat(), "reason": "x"})[0], 422, "nor bounced while held")
c.eq((journal_count(a), position(a, cust)), (mark, (D("1180.00"), D("0"))), "the refusals moved nothing")
c.eq(a.post(f"{PDC}/received/{held['id']}/cancel", {"reason": "done"})[0], 200, "it is cancelled while held")
c.eq(a.post(f"{PDC}/received/{held['id']}/cancel", {"reason": "again"})[0], 422, "a cancelled cheque cannot be cancelled again")
# a cheque dated today, banked by two requests at once: one receipt only
due = take(t.isoformat())
mark = journal_count(a)
with ThreadPoolExecutor(max_workers=2) as pool:
    answers = list(pool.map(lambda _: a.post(f"{PDC}/received/{due['id']}/deposit", deposit_body()), range(2)))
statuses = sorted(s for s, _ in answers)
c.eq(statuses[0], 200, "one of two simultaneous deposits succeeds")
c.ok(statuses[1] >= 400, "and the other is refused", statuses)
c.eq(journal_count(a), mark + 1, "exactly one journal entry was posted")
c.eq(position(a, cust), (D("0"), D("0")), "the bill is paid once: nothing owed, no advance made by a second receipt")
receipts = [r for r in all_rows(a, f"{RC}?customer_id={cust['id']}") if r["status"] == "POSTED"]
c.eq(len(receipts), 1, "one receipt exists")
c.eq(a.post(f"{PDC}/received/{due['id']}/deposit", deposit_body())[0], 422, "a later deposit is refused as well")
# the issued side
vendor = must(a.post("/api/v1/vendors", {"code": f"PD{sc.tag}", "name": f"PDC vendor {sc.tag}"}), "vendor")
issued = must(a.post(f"{PDC}/issued", {"party_id": vendor["id"], "cheque_number": suffix(7), "cheque_date": t.isoformat(), "amount": "250.00", "received_on": t.isoformat()}), "issued")
mark = journal_count(a)
body = {"deposited_on": t.isoformat(), "allocations": []}
with ThreadPoolExecutor(max_workers=2) as pool:
    answers = list(pool.map(lambda _: a.post(f"{PDC}/issued/{issued['id']}/deposit", body), range(2)))
statuses = sorted(s for s, _ in answers)
c.eq(statuses[0], 200, "one of two simultaneous presentations of an issued cheque succeeds")
c.ok(statuses[1] >= 400, "and the other is refused", statuses)
c.eq(journal_count(a), mark + 1, "exactly one payment entry was posted")
c.done()
