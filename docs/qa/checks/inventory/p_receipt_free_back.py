"""Probe (round 5): a cancelled receipt gives its free goods back to the order, and two lines of one receipt share one order line's free goods (D-BUY-67).

An order of 10 with 2 free. A receipt of two lines on the one order line, 1 free on each, is saved; the same with 2
and 1 is refused. The saved one completed puts 12 on the shelf; cancelled, the shelf is empty and the order line has
its 2 free to give again, so a new receipt may take both."""
from _inv import *
from _flow import *

c = Check("p_receipt_free_back")
w = World()
wh = w.warehouse()["id"]
p = w.product()
GR = "/api/v1/goods-receipts"

held = receive(w, wh, p["id"], 10, complete=False, po_line_extra={"free_quantity": "2"},
               line_extra={"current_receipt_quantity": "0", "free_quantity": "0"})
po = held["order"]
line_id = po["lines"][0]["id"]
# the helper's own receipt is only there to raise the order; it brought nothing and is not completed
if held["create"][0] in (200, 201):
    w.admin.post(f"{GR}/{held['receipt']['id']}/cancel", {"reason": "set-up only"})


def two_lines(first_free: str, second_free: str) -> tuple[int, Any]:
    """One receipt of two lines, five each, both on the one order line."""
    return w.admin.post(GR, {"purchase_order_id": po["id"], "receipt_date": w.today, "lines": [
        {"purchase_order_line_id": line_id, "line_number": n, "current_receipt_quantity": "5", "free_quantity": free,
         "unit_price": "60", "warehouse_id": wh} for n, free in ((1, first_free), (2, second_free))]})


st, b = two_lines("2", "1")
c.ok(st == 422 and "free" in message(b), "two lines taking 2 and 1 of the 2 free are refused together", (st, message(b)[:200]))
st, b = two_lines("1", "1")
c.ok(st in (200, 201), "two lines taking 1 free each are saved", (st, message(b)[:200]))
if st in (200, 201):
    receipt = data(b)
    c.eq(w.admin.post(f"{GR}/{receipt['id']}/complete", {})[0], 200, "and completed")
    c.eq(w.qty(p["id"], wh), D(12), "10 bought and 2 free on the shelf")
    st, b = w.admin.post(GR, {"purchase_order_id": po["id"], "receipt_date": w.today, "lines": [
        {"purchase_order_line_id": line_id, "line_number": 1, "current_receipt_quantity": "0", "free_quantity": "1",
         "unit_price": "60", "warehouse_id": wh}]})
    c.ok(st in (409, 422), "with both received, another free unit is refused", (st, message(b)[:200]))
    st, b = w.admin.post(f"{GR}/{receipt['id']}/cancel", {"reason": "wrong delivery"})
    c.eq(st, 200, "the completed receipt is cancelled: " + message(b)[:160])
    c.eq(w.qty(p["id"], wh), D(0), "the shelf is empty again")
    st, b = w.admin.post(GR, {"purchase_order_id": po["id"], "receipt_date": w.today, "lines": [
        {"purchase_order_line_id": line_id, "line_number": 1, "current_receipt_quantity": "10", "free_quantity": "2",
         "unit_price": "60", "warehouse_id": wh}]})
    c.ok(st in (200, 201), "the order line has its 2 free to give again", (st, message(b)[:200]))
    if st in (200, 201):
        c.eq(w.admin.post(f"{GR}/{data(b)['id']}/complete", {})[0], 200, "the new receipt is completed")
        c.eq(w.qty(p["id"], wh), D(12), "12 on the shelf, no more")
c.done()
