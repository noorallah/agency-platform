"""Probe (round 4): a goods receipt brings in no more free goods than its order line has left to give (D-BUY-67).

An order of 10 with 2 free: the first receipt takes 5 and both free units, the second is refused a third free unit
in words and saved without one, and the shelf holds 12. An order that promised none refuses any."""
from _inv import *
from _flow import *

c = Check("p_receipt_free_cap")
w = World()
wh = w.warehouse()["id"]
p = w.product()
GR = "/api/v1/goods-receipts"

first = receive(w, wh, p["id"], 10, complete=False, po_line_extra={"free_quantity": "2"},
                line_extra={"current_receipt_quantity": "5", "free_quantity": "2"})
c.ok(first["create"][0] in (200, 201), "5 of 10 with both free units is saved", (first["create"][0], message(first["create"][1])))
po = first["order"]
c.eq(D(po["lines"][0]["free_quantity"]), D(2), "the order line promises 2 free")
c.eq(w.admin.post(f"{GR}/{first['receipt']['id']}/complete", {})[0], 200, "and completed")
c.eq(w.qty(p["id"], wh), D(7), "5 bought and 2 free on the shelf")


def second(free: str) -> tuple[int, Any]:
    """The rest of the order, with ``free`` typed as free goods."""
    return w.admin.post(GR, {"purchase_order_id": po["id"], "receipt_date": w.today, "lines": [{
        "purchase_order_line_id": po["lines"][0]["id"], "line_number": 1, "current_receipt_quantity": "5",
        "free_quantity": free, "unit_price": "60", "warehouse_id": wh}]})


st, b = second("1")
c.ok(st == 422 and "0 left to give" in message(b) and "2 already received" in message(b),
     "a third free unit is refused, saying what the order gave and what was received", (st, message(b)[:200]))
st, b = second("0")
c.ok(st in (200, 201), "the rest is received with no free goods", (st, message(b)[:160]))
if st in (200, 201):
    c.eq(w.admin.post(f"{GR}/{data(b)['id']}/complete", {})[0], 200, "and completed")
    c.eq(w.qty(p["id"], wh), D(12), "10 bought and 2 free on the shelf, no more")

q = w.product("Q")
none = receive(w, wh, q["id"], 4, complete=False, line_extra={"free_quantity": "1"})
st, b = none["create"]
c.ok(st == 422 and "0 free on the order" in message(b), "an order that promised no free goods refuses any on its receipt", (st, message(b)[:200]))
c.eq(w.qty(q["id"], wh), D(0), "and nothing reached the shelf")
c.done()
