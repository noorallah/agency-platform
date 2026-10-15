"""TC-BUY-095: after the bought units go back off the bill, the free ones go back off the receipt."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _buy import *

c = Check("tc_buy_095")
a = admin()
sc = Scene(a)
pid = sc.product["id"]
order = sc.order(qty="10", free="2")
rc = sc.receive(order, "10", free="2")
bill = sc.bill(rc)
c.eq(D(bill["grand_total"]), D(1180), "the bill is 1,180.00")
c.eq(stock(a, pid), D(12), "12 on hand")
ret1 = sc.ret(bill, "10", kind="PURCHASE_INVOICE")
c.eq(D(ret1["grand_total"]), D(1180), "(1) 10 off the bill completes at 1,180.00")
st, body = a.post(PR, sc.return_body(rc, "3"))
c.ok(st == 422 and "can still send back 0" in message(body) and "2 free" in message(body) and "of these goods have already gone back" in message(body),
     "(2) 3 off the receipt is refused", (st, message(body)[:260]))
draft = must(a.post(PR, sc.return_body(rc, "2")), "return 2")
c.eq(D(draft["grand_total"]), D(0), "(3) the 2 save at total 0.00")
c.eq(D(draft["lines"][0]["free_quantity"]), D(2), "...as 2 free")
must(a.post(f"{PR}/{draft['id']}/approve", {}), "approve")
must(a.post(f"{PR}/{draft['id']}/complete", {}), "complete")
c.eq(stock(a, pid), D(0), "(4) nothing is on hand")
status, rep = a.get(f"{PR}/reports/reconciliation?page_size=100")
c.eq(status, 200, "the reconciliation report answers")
rows = {r["source_document_type"]: r for r in (data(rep) if status == 200 else []) if r["product_id"] == pid}
rr, bb = rows.get("GOODS_RECEIPT", {}), rows.get("PURCHASE_INVOICE", {})
c.eq([D(rr.get(k)) for k in ("received_quantity", "already_returned_quantity", "current_return_quantity", "pending_quantity")],
     [D(12), D(10), D(2), D(0)], "(4) the receipt-line row: received 12, already returned 10, returning 2, pending 0")
c.eq([D(bb.get(k)) for k in ("received_quantity", "current_return_quantity", "pending_quantity")], [D(10), D(10), D(0)],
     "the bill-line row: received 10, returning 10, pending 0")
c.done()
