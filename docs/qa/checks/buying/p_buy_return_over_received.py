"""Probe: a purchase return cannot return more than was received or than is left, or a negative quantity."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _buy import *

c = Check("p_buy_return_over_received")
a = admin()
sc = Scene(a)
pid = sc.product["id"]
order = sc.order(qty="10")
rc = sc.receive(order, "6")
over = a.post(PR, sc.return_body(rc, "7"))
c.ok(over[0] == 422 and "can still send back" in message(over[1]), "7 off a receipt of 6 is refused", (over[0], message(over[1])[:200]))
c.ok(a.post(PR, sc.return_body(rc, "-1"))[0] == 422, "a negative return is refused")
done = sc.ret(rc, "4")
c.eq(done["status"], "COMPLETED", "4 go back")
again = a.post(PR, sc.return_body(rc, "3"))
c.ok(again[0] == 422 and "can still send back 2" in message(again[1]), "3 more is refused: only 2 are left", (again[0], message(again[1])[:200]))
c.eq(stock(a, pid), D(2), "stock is 6 - 4")
c.done()
