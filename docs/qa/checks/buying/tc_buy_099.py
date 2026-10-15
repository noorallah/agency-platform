"""TC-BUY-099: a receipt brings in no more free goods than its order line has left."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _buy import *

c = Check("tc_buy_099")
a = admin()
sc = Scene(a)
pid = sc.product["id"]
order = sc.order(qty="10", free="2")
c.eq(D(order["lines"][0]["free_quantity"]), D(2), "the order promises 2 free")
first = sc.receive(order, "5", free="2")
c.eq(stock(a, pid), D(7), "(a) seven on the shelf")
over = a.post(GR, sc.receipt_body(order, "5", free="1"))
c.ok(over[0] == 422 and "0 left to give" in message(over[1]) and "2 already received" in message(over[1]),
     "(b) 5 with Free 1 is refused", (over[0], message(over[1])[:200]))
rest = sc.receive(order, "5", free="0")
c.eq(rest["status"], "COMPLETED", "with Free empty it completes")
c.eq(stock(a, pid), D(12), "the shelf holds 12")
plain = sc.order(qty="10")
none = a.post(GR, sc.receipt_body(plain, "5", free="1"))
c.ok(none[0] == 422 and "0 free on the order" in message(none[1]), "(c) the order promised none: refused", (none[0], message(none[1])[:200]))
must(a.post(f"{GR}/{first['id']}/cancel", {"reason": "check"}), "cancel")
again = a.post(GR, sc.receipt_body(order, "5", free="2"))
c.ok(again[0] in (200, 201), "(d) after the cancel, 5 with Free 2 is accepted", (again[0], message(again[1])[:200]))
if again[0] in (200, 201):
    third = a.post(GR, sc.receipt_body(order, "1", free="1"))
    c.ok(third[0] == 422, "a draft receipt counts against the line", (third[0], message(third[1])[:160]))
c.done()
