"""Probe (b): salesman required: refused by name without one, accepted with one, and the return inherits it."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sell import *

c = Check("p_sell_salesman_required")
a = admin()
sc = Scene(a, stock="100")
sm = salesman(a, sc.tag)
order_body = {
    "customer_id": sc.customer["id"], "order_date": today().isoformat(),
    "branch_id": sc.branch["id"], "warehouse_id": sc.warehouse["id"],
    "lines": [{"line_number": 1, "product_id": sc.product["id"], "quantity": "2"}]}
with counter(a, salesman_required=True):
    c.refused(a.post(SI, sc.bill_body("1")), 422, "salesman", "a bill without a salesman is refused by name")
    ok = a.post(SI, sc.bill_body("3", salesman_id=sm["id"]))
    c.eq(ok[0], 201, f"a bill with a salesman is accepted ({message(ok[1])})")
    bill = must(a.post(f"{SI}/{data(ok[1])['id']}/approve", {}), "approve") if ok[0] == 201 else None
    if bill:
        c.eq(bill["salesman_id"], sm["id"], "the bill keeps the salesman")
        ret = a.post(SR, return_body(sc, bill, "1"))
        c.eq(ret[0], 201, f"the return is accepted without naming one ({message(ret[1])})")
        if ret[0] == 201:
            c.eq(data(ret[1])["salesman_id"], sm["id"], "the return inherits the bill's salesman")
with settings(a, salesman_required=True):
    c.refused(a.post(SO, order_body), 422, "salesman", "an order without a salesman is refused by name")
    ok = a.post(SO, {**order_body, "salesman_id": sm["id"]})
    c.eq(ok[0], 201, f"an order with a salesman is accepted ({message(ok[1])})")
    if ok[0] == 201:
        o = must(a.post(f"{SO}/{data(ok[1])['id']}/approve", {}), "approve")
        note = new_note(sc, o, "2")
        c.eq(note["salesman_id"], sm["id"], "the delivery note inherits the order's salesman")
off = a.post(SO, order_body)
c.eq(off[0], 201, "with the switch off again an order needs none")
c.done()
