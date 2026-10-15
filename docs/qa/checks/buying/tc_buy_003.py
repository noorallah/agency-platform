"""TC-BUY-003: receiving part of an order, then the rest; a line of 0 is refused."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _buy import *

c = Check("tc_buy_003")
a = admin()
sc = Scene(a)
pid = sc.product["id"]
order = sc.order()
first = sc.receive(order, "4", complete=False)
c.eq(first["status"], "DRAFT", "a saved receipt is a draft")
c.eq(D(first["lines"][0]["previously_received_quantity"]), D(0), "already received 0")
c.eq(D(first["lines"][0]["ordered_quantity"]), D(10), "ordered 10")
c.eq(stock(a, pid), D(0), "a draft moves no stock")
done = must(a.post(f"{GR}/{first['id']}/complete", {}), "complete")
c.eq(done["status"], "COMPLETED", "completed")
c.eq(sc.reload(order)["status"], "PARTIALLY_RECEIVED", "the order reads PARTIALLY_RECEIVED")
c.eq(stock(a, pid), D(4), "MAIN holds 4")
rows = [r for r in ledger(a, pid) if r["transaction_type"] == "GOODS_RECEIPT"]
c.eq([D(r["quantity"]) for r in rows], [D(4)], "the ledger shows GOODS_RECEIPT 4")
second = sc.receive(order, "6", complete=False)
c.eq(D(second["lines"][0]["previously_received_quantity"]), D(4), "the second receipt says already received 4")
must(a.post(f"{GR}/{second['id']}/complete", {}), "complete 2")
c.eq(sc.reload(order)["status"], "RECEIVED", "the order reads RECEIVED")
c.eq(stock(a, pid), D(10), "MAIN holds 10")
rows = [r for r in ledger(a, pid) if r["transaction_type"] == "GOODS_RECEIPT"]
c.eq(len(rows), 2, "two GOODS_RECEIPT ledger entries")
# a line of 0 with nothing free is refused on an order, a receipt, a bill and a return
c.refused(a.post(PO, sc.order_body(qty="0")), 422, "orders a quantity of 0 and nothing free", "an order line of 0")
fresh = sc.order()
c.refused(a.post(GR, sc.receipt_body(fresh, "0")), 422, "quantity of 0", "a receipt line of 0")
rcpt = sc.receive(fresh, "5")
c.refused(a.post(PI, sc.bill_body(rcpt, qty="0")), 422, "quantity of 0", "a bill line of 0")
c.refused(a.post(PR, sc.return_body(rcpt, "0")), 422, "quantity of 0", "a return line of 0")
c.done()
