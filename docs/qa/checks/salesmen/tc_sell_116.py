"""TC-SELL-116: 'Salesman required' refuses an order, a note and a bill without one."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sm import *

SAYS = "requires a salesman"
c = Check("tc_sell_116")
a = admin()
sc = Scene(a, stock="200")
plain = sc.new_customer()  # no account manager, no round

# An order saved while the switch is off, for the note to be raised from.
order = must(a.post(SO, sc.order_body("2", customer=plain)), "order, switch off")
must(a.post(f"{SO}/{order['id']}/approve", {}), "approve")
line = must(a.get(f"{SO}/{order['id']}"), "read")["lines"][0]
note_body = {
    "sales_order_id": order["id"],
    "delivery_date": today().isoformat(),
    "lines": [{"sales_order_line_id": line["id"], "line_number": 1, "current_delivery_quantity": "2"}],
}

with settings(a, salesman_required=True):
    c.refused(a.post(SO, sc.order_body("1", customer=plain)), 422, SAYS, "order without a salesman, switch on")
    c.refused(a.post(DN, note_body), 422, SAYS, "delivery note without a salesman, switch on")
    status, body = a.post(QT, sc.quote_body("1"))
    c.eq(status, 201, f"a quotation saves with the switch on ({message(body)[:150]})")
    # Nothing was saved by the refused order.
    before = data(a.get(f"{SO}?customer_id={plain['id']}&page_size=50")[1])
    c.eq(len(before), 1, "the refused order left nothing behind")
with settings(a, salesman_required=True, sales_order_stage=False, delivery_note_stage=False):
    c.refused(a.post(SI, sc.bill_body("1", customer=plain)), 422, SAYS, "bill without a salesman, switch on")
    # The order saved earlier is untouched by the switch.
    again = must(a.get(f"{SO}/{order['id']}"), "order again")
    c.eq(again.get("status"), "APPROVED", "an older order is untouched")

# Switch off: all three save.
status, body = a.post(SO, sc.order_body("1", customer=plain))
c.eq(status, 201, f"order saves with the switch off ({message(body)[:150]})")
status, body = a.post(DN, note_body)
c.eq(status, 201, f"delivery note saves with the switch off ({message(body)[:150]})")
with counter(a):
    status, body = a.post(SI, sc.bill_body("1", customer=plain))
    c.eq(status, 201, f"bill saves with the switch off ({message(body)[:150]})")
c.done()
