"""Probe (c): there is no approval switch for a sales return; a return still goes draft, approve, complete."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sell import *

c = Check("p_sell_return_approval")
a = admin()
held = must(a.get(SETTINGS), "settings")
c.eq(sorted(k for k in held if k.endswith("_approval") and "outlet" not in k), ["delivery_note_approval", "sales_invoice_approval", "sales_order_approval"], "the settings offer three approval switches and none for a return")
sc = Scene(a, stock="50")
with counter(a, sales_order_approval=False, delivery_note_approval=False, sales_invoice_approval=False):
    bill = sc.bill(qty="3")
    made = must(a.post(SR, return_body(sc, bill, "1")), "return")
    c.eq(made["status"], "DRAFT", "a return saves as a draft whatever the other switches say")
    skip = a.post(f"{SR}/{made['id']}/complete", {})
    c.ok(skip[0] in (409, 422), "completing a draft without approving it is refused", f"{skip[0]} {message(skip[1])}")
    c.eq(must(a.post(f"{SR}/{made['id']}/approve", {}), "approve")["status"], "APPROVED", "approve")
    c.eq(must(a.post(f"{SR}/{made['id']}/complete", {}), "complete")["status"], "COMPLETED", "complete")
c.done()
