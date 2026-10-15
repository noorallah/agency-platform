"""TC-BUY-066: a 10+2 scheme fills the free quantity on the order."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _buy import *

c = Check("tc_buy_066")
a = admin()
sc = Scene(a)
pid = sc.product["id"]
scheme = must(a.post("/api/v1/supplier-schemes", {
    "vendor_id": sc.vendor["id"], "product_id": pid, "buy_quantity": "10", "free_quantity": "2",
    "valid_from": today().isoformat(),
}), "scheme")
c.ok(scheme.get("is_active", True), "the scheme is in force")
order = sc.order(approve=False, qty="25")
line = order["lines"][0]
c.eq(D(line["free_quantity"]), D(4), "the order line's Free reads 4 (two free for each full ten)")
c.eq(line.get("scheme_id"), scheme["id"], "the line records the scheme")
c.eq(D(line["gross_amount"]) if "gross_amount" in line else D(order["subtotal"]), D(2500), "charged 25 x 100 = 2,500.00 before tax")
must(a.post(f"{PO}/{order['id']}/submit", {}), "submit")
must(a.post(f"{PO}/{order['id']}/approve", {}), "approve")
order = sc.reload(order)
rbody = sc.receipt_body(order, "25", free="4")
c.eq(D(must(a.get(f"{PO}/{order['id']}"), "o")["lines"][0]["free_quantity"]), D(4), "still 4 free after approval")
rc = must(a.post(GR, rbody), "receipt")
rc = must(a.post(f"{GR}/{rc['id']}/complete", {}), "complete")
c.eq(stock(a, pid), D(29), "after Complete 29 are on hand")
gj = journal(a, rc["grn_number"])
c.ok(len(gj) >= 1, "the receipt has a journal")
if gj:
    net = entry_net(a, gj[0])
    c.eq(net.get("INVENTORY"), D(2500), "Dr Inventory 2,500.00 (free goods add units, not value)")
    c.eq(net.get("GOODS_RECEIVED_NOT_INVOICED"), D(-2500), "Cr Goods Received Not Invoiced 2,500.00")
c.refused(a.post(PR, sc.return_body(rc, "30")), 422, "bought and 4 free", "30 is refused (the server prints 25 PIECE bought)")
ret = sc.ret(rc, "29")
c.eq(ret["status"], "COMPLETED", "a return of all 29 is accepted")
c.eq(D(ret["subtotal"]), D(2500), "and prices the 25 bought: 2,500.00")
c.eq(stock(a, pid), D(0), "nothing left on hand")
c.done()
