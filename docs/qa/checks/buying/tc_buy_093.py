"""TC-BUY-093: free goods go back off the goods receipt that brought them in."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _buy import *

c = Check("tc_buy_093")
a = admin()
sc = Scene(a)
pid = sc.product["id"]
o1 = sc.order(qty="10", free="2")
o2 = sc.order(qty="10", free="2")
g1 = sc.receive(o1, "10", free="2")
g2 = sc.receive(o2, "10", free="2")
c.eq(stock(a, pid), D(24), "24 on hand")
# (1) 13 off the first receipt is refused
st, body = a.post(PR, sc.return_body(g1, "13"))
c.ok(st == 422 and "can still send back 10" in message(body) and "2 free" in message(body), "(1) 13 off a receipt of 10 + 2 free is refused", (st, message(body)[:200]))
# (2) 12 is accepted at 1,000.00 gross
draft = must(a.post(PR, sc.return_body(g1, "12")), "return 12")
c.eq(D(draft["subtotal"]), D(1000), "(2) the gross is 1,000.00, on the 10 bought only")
c.eq(D(draft["grand_total"]), D(1180), "total 1,180.00")
must(a.post(f"{PR}/{draft['id']}/approve", {}), "approve")
done = must(a.post(f"{PR}/{draft['id']}/complete", {}), "complete")
c.eq(stock(a, pid), D(12), "12 are on hand after Complete")
rj = journal(a, done["return_number"])
c.ok(len(rj) >= 1, "the return has a journal")
if rj:
    net = entry_net(a, rj[0])
    c.eq(net.get("GOODS_RECEIVED_NOT_INVOICED"), D(1000), "Dr Goods Received Not Invoiced 1,000.00")
    c.eq(net.get("INVENTORY"), D(-1000), "Cr Inventory 1,000.00")
status, rep = a.get(f"{PR}/reports/reconciliation?page_size=100")
c.eq(status, 200, "the reconciliation report answers")
row = next((r for r in (data(rep) if status == 200 else []) if r["source_document_id"] == g1["id"]), {})
c.eq([D(row.get(k)) for k in ("received_quantity", "current_return_quantity", "pending_quantity")], [D(12), D(12), D(0)],
     "the reconciliation counts the free goods: received 12, returning 12, pending 0")
# (3) only the free units go back off the second receipt
free_only = must(a.post(PR, sc.return_body(g2, "2", free="2")), "free-only return")
c.eq(D(free_only["grand_total"]), D(0), "(3) a return of only the free units totals 0.00")
must(a.post(f"{PR}/{free_only['id']}/approve", {}), "approve")
must(a.post(f"{PR}/{free_only['id']}/complete", {}), "complete")
c.eq(stock(a, pid), D(10), "stock falls by 2: 10 on hand")
# (4) a bill of the second receipt: only what was billed goes back off the bill
bill = sc.bill(g2)
c.eq(D(bill["grand_total"]), D(1180), "the bill is 1,180.00")
st, body = a.post(PR, sc.return_body(bill, "11", kind="PURCHASE_INVOICE"))
c.ok(st == 422 and "free goods go back off the goods receipt" in message(body), "(4) 11 off the bill is refused", (st, message(body)[:200]))
c.done()
