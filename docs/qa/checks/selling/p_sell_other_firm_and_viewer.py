"""Probe (f): another firm's order, note, bill and return are 404/403, and a Viewer cannot create."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sell import *

c = Check("p_sell_other_firm_and_viewer")
a = admin()
b = admin("admin2")
v = admin("viewer")
sc = Scene(a, stock="100")
order = new_order(sc, "5", approve=True)
note = new_note(sc, order, "5", dispatch=True)
bill = bill_note(sc, note, "5")
ret = must(a.post(SR, return_body(sc, bill, "1")), "return")
for what, path, doc in (("order", SO, order), ("note", DN, note), ("bill", SI, bill), ("return", SR, ret)):
    c.eq(b.get(f"{path}/{doc['id']}")[0], 404, f"firm two cannot read firm one's {what}")
    c.eq(a.inside(b.firm_id).get(f"{path}/{doc['id']}")[0], 403, f"firm one naming firm two's id is refused for the {what}")
    c.eq(v.get(f"{path}/{doc['id']}")[0], 200, f"a Viewer reads the {what}")
c.eq(b.post(f"{SO}/{order['id']}/cancel", {"reason": "x"})[0], 404, "firm two cannot cancel firm one's order")
c.eq(b.post(f"{SI}/{bill['id']}/cancel", {"reason": "x"})[0], 404, "nor its bill")
c.eq(b.post(f"{SR}/{ret['id']}/approve", {})[0], 404, "nor approve its return")
cn = b.post(CN, {"sales_invoice_id": bill["id"], "credit_note_date": today().isoformat(), "reason": "OTHER",
    "lines": [{"sales_invoice_line_id": bill["lines"][0]["id"], "line_number": 1, "taxable_amount": "1"}]})
c.ok(cn[0] in (403, 404, 422), "nor raise a credit note against its bill", f"{cn[0]} {message(cn[1])}")
c.eq(b.post(PF, {"sales_order_id": order["id"], "proforma_date": today().isoformat()})[0] in (404, 422), True, "nor a proforma of its order")
# a Viewer cannot create anything
c.eq(v.post(SO, {"customer_id": sc.customer["id"], "order_date": today().isoformat(), "branch_id": sc.branch["id"],
    "warehouse_id": sc.warehouse["id"], "lines": [{"line_number": 1, "product_id": sc.product["id"], "quantity": "1"}]})[0], 403, "a Viewer cannot raise an order")
c.eq(v.post(SI, sc.bill_body("1"))[0], 403, "a Viewer cannot raise a bill")
c.eq(v.post(SR, return_body(sc, bill, "1"))[0], 403, "a Viewer cannot raise a return")
c.eq(v.post(DN, {"sales_order_id": order["id"], "delivery_date": today().isoformat(), "lines": [
    {"sales_order_line_id": order["lines"][0]["id"], "line_number": 1, "current_delivery_quantity": "1"}]})[0], 403, "a Viewer cannot raise a note")
c.eq(v.post(f"{SO}/{order['id']}/hold", {"reason": "x"})[0], 403, "a Viewer cannot hold an order")
c.eq(v.post(f"{SR}/{ret['id']}/approve", {})[0], 403, "a Viewer cannot approve a return")
c.done()
