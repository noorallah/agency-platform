"""TC-BUY-011: a return off a bill already paid leaves a supplier credit."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _buy import *

c = Check("tc_buy_011")
a = admin()
sc = Scene(a)
order = sc.order()
sc.receive(order, "4")
r6 = sc.receive(order, "6")
bill = sc.bill(r6)
c.eq(sc.pay("708", bill)[0], 201, "the bill is paid in full")
ret = sc.ret(bill, "2", kind="PURCHASE_INVOICE")
c.eq(ret["status"], "COMPLETED", "the return off the paid bill completes")
vid = sc.vendor["id"]
c.eq(owing(a, vid, bill["id"]), D(0), "the paid bill does not reappear in Record Payment")
credits = rows_of(a.get(f"{PAY}/supplier-credits?vendor_id={vid}"))
mine = [r for r in credits if r["purchase_return_id"] == ret["id"]]
c.eq(len(mine), 1, "the return appears as a supplier credit")
if mine:
    c.eq(D(mine[0]["available_amount"]), D(236), "for its value, 236.00")
# deleting the supplier is refused while the credit stands
gone = a.delete(f"/api/v1/vendors/{vid}")
c.ok(gone[0] in (409, 422), "deleting the supplier is refused while the credit stands", (gone[0], message(gone[1])[:120]))
# another bill, and the credit applied to it
order2 = sc.order()
r2 = sc.receive(order2, "10")
bill2 = sc.bill(r2)
c.eq(D(bill2["grand_total"]), D(1180), "the second bill is 1,180.00")
c.eq(owing(a, vid, bill2["id"]), D(1180), "it owes 1,180.00")
gone = a.delete(f"/api/v1/vendors/{vid}")
c.ok(gone[0] in (409, 422), "still refused with the open bill", gone[0])
applied = a.post(f"{PAY}/supplier-credits/{ret['id']}/apply", {"invoice_id": bill2["id"], "amount": "236"})
c.ok(applied[0] in (200, 201), "the credit is applied", (applied[0], message(applied[1])))
c.eq(owing(a, vid, bill2["id"]), D(944), "the new bill owes 236.00 less: 944.00")
c.done()
