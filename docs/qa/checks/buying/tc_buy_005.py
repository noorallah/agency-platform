"""TC-BUY-005: a receipt that has been invoiced cannot be cancelled."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _buy import *

c = Check("tc_buy_005")
a = admin()
sc = Scene(a)
pid = sc.product["id"]
order = sc.order()
sc.receive(order, "4")
r6 = sc.receive(order, "6")
bill = sc.bill(r6)
c.eq(D(bill["grand_total"]), D(708), "the bill is 708.00")
c.refused(a.post(f"{GR}/{r6['id']}/cancel", {"reason": "check"}), 422, "has been invoiced", "cancelling an invoiced receipt")
c.eq(must(a.get(f"{GR}/{r6['id']}"), "read")["status"], "COMPLETED", "the receipt is still completed")
c.eq(stock(a, pid), D(10), "stock is unchanged")
c.eq(must(a.get(f"{PI}/{bill['id']}"), "bill")["status"], "APPROVED", "the bill is unchanged")
c.done()
