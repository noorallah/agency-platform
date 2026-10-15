"""TC-BUY-010: a return to be replaced reopens the order."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _buy import *

c = Check("tc_buy_010")
a = admin()
sc = Scene(a)
order = sc.order()
sc.receive(order, "4")
r6 = sc.receive(order, "6")
c.eq(sc.reload(order)["status"], "RECEIVED", "the order is fully received")
ret = sc.ret(r6, "2", outcome="REPLACEMENT")
after = sc.reload(order)
c.eq(after["status"], "PARTIALLY_RECEIVED", "a replacement return reopens the order")
c.eq(D(after["lines"][0]["pending_receipt_quantity"]), D(2), "2 are pending")
more = sc.receive(order, "2")
c.eq(more["status"], "COMPLETED", "the replacement receipt of 2 is accepted")
c.eq(sc.reload(order)["status"], "RECEIVED", "the order reads Received again")
# changing the outcome to Credit before receiving puts the order back to Received
order2 = sc.order()
sc.receive(order2, "4")
r2 = sc.receive(order2, "6")
ret2 = sc.ret(r2, "2", outcome="REPLACEMENT")
c.eq(sc.reload(order2)["status"], "PARTIALLY_RECEIVED", "second order reopened")
changed = a.post(f"{PR}/{ret2['id']}/outcome", {"outcome": "CREDIT"})
c.eq(changed[0], 200, "the outcome is changed to Credit")
c.eq(sc.reload(order2)["status"], "RECEIVED", "the order goes back to Received")
c.done()
