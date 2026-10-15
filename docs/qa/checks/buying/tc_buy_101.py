"""TC-BUY-101: approval switched off for a buying document: one Save completes it, only for whoever raised it.

Over the API a screen's single Save is create + submit + approve (or + complete); the
screen wording and which buttons are offered are not checked.
"""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _buy import *

c = Check("tc_buy_101")
f = admin()            # F, the firm administrator
b = admin("exec")      # B, a Purchase Executive
sc = Scene(f)
pid = sc.product["id"]
wid = sc.warehouse["id"]
sb = Scene.__new__(Scene)  # the same records, driven as B
sb.__dict__.update(sc.__dict__)
sb.api = b


def raise_as(who: Scene, qty: str = "5", price: str = "60") -> dict:
    """Create a draft order of the item (no submit) as the scene's user."""
    return must(who.api.post(PO, who.order_body(qty=qty, price=price)), "order")


def state_of(order: dict) -> str:
    """Read an order's status."""
    return must(f.get(f"{PO}/{order['id']}"), "order")["status"]


# 1. B cannot change the settings
c.eq(b.put(SETTINGS, {"purchase_order_stage": True, "goods_receipt_stage": True})[0], 403, "(1) B cannot change the settings")
with settings(f, purchase_order_approval=True, goods_receipt_approval=True, purchase_invoice_approval=True,
              purchase_order_stage=True, goods_receipt_stage=True):
    # 2. switch the order approval off
    must(f.put(SETTINGS, {**{k: v for k, v in data(f.get(SETTINGS)[1]).items() if k != "is_configured"}, "purchase_order_approval": False}), "switch off")
    got = data(f.get(SETTINGS)[1])
    c.eq(got["purchase_order_approval"], False, "(2) the order switch is off and the others stay on")
    c.eq((got["goods_receipt_approval"], got["purchase_invoice_approval"]), (True, True), "the other two switches are still on")
    # 3. B raises an order; one Save leaves it Approved
    ob = raise_as(sb)
    must(b.post(f"{PO}/{ob['id']}/submit", {}), "submit")
    done = b.post(f"{PO}/{ob['id']}/approve", {})
    c.eq(done[0], 200, "(3) B approves the order he raised")
    c.eq(state_of(ob), "APPROVED", "the order is Approved")
    # a second one left submitted by B
    left = raise_as(sb)
    must(b.post(f"{PO}/{left['id']}/submit", {}), "submit")
    # 4. F's submitted order cannot be approved by B
    of = raise_as(sc)
    must(f.post(f"{PO}/{of['id']}/submit", {}), "submit")
    c.refused(b.post(f"{PO}/{of['id']}/approve", {}), 403, "Only whoever raised this purchase order may approve it without PURCHASE_APPROVE", "(4) B approving F's order")
    # 5. switch on again
    must(f.put(SETTINGS, {**{k: v for k, v in data(f.get(SETTINGS)[1]).items() if k != "is_configured"}, "purchase_order_approval": True}), "switch on")
    o5 = raise_as(sb)
    must(b.post(f"{PO}/{o5['id']}/submit", {}), "submit")
    c.eq(state_of(o5), "SUBMITTED", "(5) the order stays Submitted")
    c.refused(b.post(f"{PO}/{o5['id']}/approve", {}), 403, "waits for approval, which needs PURCHASE_APPROVE", "B approving with the switch on")
    c.eq(b.post(f"{PO}/{left['id']}/approve", {})[0], 200, "the order B left submitted while the switch was off can still be approved by B")
    # 6. F approves B's order of step 5
    c.eq(f.post(f"{PO}/{o5['id']}/approve", {})[0], 200, "(6) F approves B's order")
    # 7. goods receipts: the receipt has no approver, so the server answers Complete the same with the
    #    switch on or off; "one Save completes it" is the screen's behaviour and is not checked here.
    ob = sc.reload(ob)
    must(f.put(SETTINGS, {**{k: v for k, v in data(f.get(SETTINGS)[1]).items() if k != "is_configured"}, "goods_receipt_approval": False}), "switch receipts off")
    rb2 = must(b.post(GR, sb.receipt_body(ob, "3")), "receipt")
    c.eq(b.post(f"{GR}/{rb2['id']}/complete", {})[0], 200, "(7) B completes his own receipt")
    c.eq(stock(f, pid), D(3), "stock of P rises by 3")
    print("note: step 7 one-Save completion of a receipt is a screen behaviour; not driven")
    # 8. stages off, default warehouse W, bill approval off: B's bill is Approved
    must(f.put(SETTINGS, {**{k: v for k, v in data(f.get(SETTINGS)[1]).items() if k != "is_configured"},
                          "purchase_order_stage": False, "goods_receipt_stage": False, "default_warehouse_id": wid,
                          "purchase_invoice_approval": False}), "stages off")
    manual = {
        "vendor_id": sc.vendor["id"], "branch_id": sc.branch["id"], "invoice_date": today().isoformat(),
        "supplier_invoice_number": f"M-{sc.tag}1", "supplier_invoice_date": today().isoformat(),
        "lines": [{"source_document_type": "MANUAL", "product_id": pid, "line_number": 1,
                   "current_invoice_quantity": "3", "unit_price": "60", "warehouse_id": wid}],
    }
    mb = b.post(PI, manual)
    c.ok(mb[0] == 201, "(8) B types a bill with no order or receipt", (mb[0], message(mb[1])[:200]))
    if mb[0] == 201:
        bid = data(mb[1])["id"]
        ap = b.post(f"{PI}/{bid}/approve", {})
        c.eq(ap[0], 200, "B approves his own bill")
        c.eq(must(f.get(f"{PI}/{bid}"), "bill")["status"], "APPROVED", "the bill is Approved")
        c.eq(stock(f, pid), D(6), "stock of P rises by 3 more")
    # 9. F's draft bill cannot be approved by B
    fb = f.post(PI, {**manual, "supplier_invoice_number": f"M-{sc.tag}2"})
    if fb[0] == 201:
        c.refused(b.post(f"{PI}/{data(fb[1])['id']}/approve", {}), 403, "Only whoever raised", "(9) B approving F's bill")
    else:
        c.ok(False, "(9) F can type a bill", (fb[0], message(fb[1])[:160]))
    # 10. bill approval back on: B's bill stays a draft
    must(f.put(SETTINGS, {**{k: v for k, v in data(f.get(SETTINGS)[1]).items() if k != "is_configured"}, "purchase_invoice_approval": True}), "bill switch on")
    b10 = b.post(PI, {**manual, "supplier_invoice_number": f"M-{sc.tag}3"})
    if b10[0] == 201:
        bid = data(b10[1])["id"]
        c.refused(b.post(f"{PI}/{bid}/approve", {}), 403, "waits for approval, which needs PURCHASE_APPROVE", "(10) B approving with the bill switch on")
        c.eq(must(f.get(f"{PI}/{bid}"), "bill")["status"], "DRAFT", "the bill stays a Draft")
    else:
        c.ok(False, "(10) B can type a bill", (b10[0], message(b10[1])[:160]))
# 11. everything back as it was
after = data(f.get(SETTINGS)[1])
c.eq((after["purchase_order_approval"], after["goods_receipt_approval"], after["purchase_invoice_approval"],
      after["purchase_order_stage"], after["goods_receipt_stage"]), (True, True, True, True, True), "(11) the settings are back as they were")
c.done()
