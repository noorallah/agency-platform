"""TC-BUY-096: a return takes its receipt line's batch, and no other.

The case names a Pharmacy firm; the batch rules are the same on the Wholesale check
firm, so a batch-tracked product is made there. Expiry dates are not sent.
"""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _buy import *

c = Check("tc_buy_096")
a = admin()
sc = Scene(a)
sc.product = sc.new_product("T", track_batch=True, require_batch_on_receipt=True)
pid = sc.product["id"]


def batch_qty(number: str) -> Decimal:
    """Return what a batch holds."""
    rows = rows_of(a.get(f"/api/v1/batch-serial/batches?product_id={pid}&search={number}&page_size=50"))
    return sum((D(r["quantity"]) for r in rows if r["batch_number"] == number), Decimal(0))


gx = sc.receive(sc.order(qty="10"), "10", batch_number="QA-X")
gy = sc.receive(sc.order(qty="5"), "5", batch_number="QA-Y")
c.eq((batch_qty("QA-X"), batch_qty("QA-Y")), (D(10), D(5)), "QA-X holds 10 and QA-Y holds 5")
# (1) a line naming no batch takes its receipt line's batch
made = must(a.post(PR, sc.return_body(gx, "2")), "return")
c.eq(made["lines"][0]["batch_number"], "QA-X", "(1) the draft reads QA-X")
must(a.post(f"{PR}/{made['id']}/approve", {}), "approve")
must(a.post(f"{PR}/{made['id']}/complete", {}), "complete")
c.eq(batch_qty("QA-X"), D(8), "after Complete the batch holds 8")
# (2) another batch is refused at Save, and nothing is written
count = len(rows_of(a.get(f"{PR}?vendor_id={sc.vendor['id']}&page_size=50")))
words = "brought these goods in as batch QA-X, so batch QA-Y cannot go back against it"
c.refused(a.post(PR, sc.return_body(gx, "2", batch_number="QA-Y")), 422, words, "(2) QA-Y off the receipt of QA-X")
c.eq(len(rows_of(a.get(f"{PR}?vendor_id={sc.vendor['id']}&page_size=50"))), count, "nothing was written")
c.eq(batch_qty("QA-Y"), D(5), "QA-Y still holds 5")
# (3) a batch nobody received
c.refused(a.post(PR, sc.return_body(gx, "2", batch_number="NO-SUCH-BATCH")), 422, "NO-SUCH-BATCH", "(3) a batch nobody received")
# (4) PUT a draft naming QA-Y
draft = must(a.post(PR, sc.return_body(gx, "1")), "draft")
body = sc.return_body(gx, "1", batch_number="QA-Y")
put = a.put(f"{PR}/{draft['id']}", body)
c.refused(put, 422, words, "(4) a PUT of the draft naming QA-Y")
c.eq(must(a.get(f"{PR}/{draft['id']}"), "read")["lines"][0]["batch_number"], "QA-X", "the draft still reads QA-X")
# the same holds off the bill line
bill = sc.bill(gx, qty="8")
c.refused(a.post(PR, sc.return_body(bill, "1", kind="PURCHASE_INVOICE", batch_number="QA-Y")), 422, "cannot go back against it", "off the bill line too")
c.done()
