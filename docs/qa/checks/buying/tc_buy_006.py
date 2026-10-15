"""TC-BUY-006: returning damaged goods to the supplier.

Skipped with a note: the final refusal (more than the location holds) needs stock
to leave by a route this module does not drive (a sale or an issue).
"""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _buy import *

c = Check("tc_buy_006")
a = admin()
sc = Scene(a)
pid = sc.product["id"]
order = sc.order()
sc.receive(order, "4")
r6 = sc.receive(order, "6")
made = must(a.post(PR, sc.return_body(r6, "2", is_damaged=True)), "return")
c.eq(made["status"], "DRAFT", "a saved return is a draft")
c.eq(stock(a, pid), D(10), "a draft takes nothing off")
must(a.post(f"{PR}/{made['id']}/approve", {}), "approve")
done = must(a.post(f"{PR}/{made['id']}/complete", {}), "complete")
c.eq(done["status"], "COMPLETED", "COMPLETED")
c.eq(stock(a, pid), D(8), "MAIN holds 8")
rows = [r for r in ledger(a, pid) if r["transaction_type"] == "RETURN"]
c.eq([D(r["quantity"]) for r in rows], [D(2)], "the ledger shows the return of 2")
c.ok(len(journal(a, made["return_number"])) >= 1, "the return has a journal entry")
c.eq(done["lines"][0].get("is_damaged"), True, "the line is flagged damaged")
status, rep = a.get(f"{PR}/reports/damaged?page_size=100")
c.eq(status, 200, "the damaged-goods report answers")
if status == 200:
    c.ok(made["return_number"] in str(rep) or str(made["id"]) in str(rep), "the damaged-goods report lists the return", str(rep)[:200])
c.eq(done["lines"][0]["product_id"], pid, "the return line names the product")
print("note: more-than-held refusal at Complete not driven (needs stock to leave another way)")
c.done()
