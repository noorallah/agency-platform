"""Probe (a): a stage switched off is raised by the chain: a bill still has its real order and note, and stock leaves at dispatch."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sell import *

c = Check("p_sell_stage_off")
a = admin()
# D-SELL-103: the pair "order off, note on" is refused at save, and nothing changes.
before = data(a.get(SETTINGS)[1])
keys = ("quotation_stage", "sales_order_stage", "delivery_note_stage", "default_branch_id",
        "default_warehouse_id", "promotion_mode", "max_line_discount_percent", "rate_includes_tax",
        "new_outlets_need_approval", "reservation_lapse_days", "sales_order_approval",
        "delivery_note_approval", "sales_invoice_approval", "round_bills_to_rupee",
        "salesman_required", "box_and_piece_entry")
body = {k: before[k] for k in keys if k in before}
body.update(sales_order_stage=False, delivery_note_stage=True)
refused = a.put(SETTINGS, body)
c.eq(refused[0], 422, "order off, note on: refused at save (D-SELL-103)")
c.ok("Sales order" in message(refused[1]), "the refusal names the Sales order stage", message(refused[1])[:90])
after = data(a.get(SETTINGS)[1])
c.eq((after["sales_order_stage"], after["delivery_note_stage"]), (before["sales_order_stage"], before["delivery_note_stage"]), "the stages are unchanged")
for order_stage, note_stage in ((False, False), (True, False)):
    label = f"order={order_stage} note={note_stage}"
    sc = Scene(a, stock="50")
    pid = sc.product["id"]
    with settings(a, sales_order_stage=order_stage, delivery_note_stage=note_stage):
        if order_stage and not note_stage:
            # a bill of an approved order: the note is raised behind it
            ordered = new_order(sc, "4", approve=True)
            oline = ordered["lines"][0]
            made = a.post(SI, {"customer_id": sc.customer["id"], "branch_id": sc.branch["id"],
                "invoice_date": today().isoformat(),
                "source_documents": [{"source_document_type": "SALES_ORDER", "source_document_id": ordered["id"]}],
                "lines": [{"source_document_type": "SALES_ORDER", "source_document_id": ordered["id"],
                           "source_document_line_id": oline["id"], "line_number": 1, "current_invoice_quantity": "4"}]})
        else:
            made = a.post(SI, sc.bill_body("4"))
        if made[0] != 201 and not order_stage and note_stage:
            bare = a.post(DN, {"customer_id": sc.customer["id"], "branch_id": sc.branch["id"], "delivery_date": today().isoformat(),
                "warehouse_id": sc.warehouse["id"], "lines": [{"line_number": 1, "product_id": sc.product["id"], "current_delivery_quantity": "4"}]})
            c.ok(False, f"{label}: some document can be typed (a bare bill is refused, and so is a note with no order)", f"{made[0]} {message(made[1])[:90]} | note {bare[0]}")
            continue
        if made[0] != 201:
            c.ok(False, f"{label}: a bare bill is accepted", f"{made[0]} {message(made[1])}")
            continue
        bill = data(made[1])
        c.eq(stock(a, pid)[0], D(50), f"{label}: the draft moves nothing")
        done = a.post(f"{SI}/{bill['id']}/approve", {})
        if done[0] != 200:
            c.ok(False, f"{label}: the bill approves", f"{done[0]} {message(done[1])}")
            continue
        c.eq(stock(a, pid), (D(46), D(0)), f"{label}: stock left at dispatch, nothing stays reserved")
        orders = rows_of(a.get(f"{SO}?customer_id={sc.customer['id']}&page_size=50"))
        notes = rows_of(a.get(f"{DN}?customer_id={sc.customer['id']}&page_size=50"))
        c.eq(len(orders), 1, f"{label}: the real order exists")
        c.eq(len(notes), 1, f"{label}: the real delivery note exists")
        if orders and notes:
            c.eq((orders[0]["status"], notes[0]["status"]), ("DELIVERED", "DISPATCHED"), f"{label}: order delivered, note dispatched")
            c.eq(D(notes[0]["grand_total"]), D(bill["grand_total"]), f"{label}: the note carries the bill's value")
        c.ok(len(journal(a, bill["invoice_number"])) == 1, f"{label}: the bill has its journal")
        c.ok(any(r["transaction_type"] == "DISPATCH" for r in ledger(a, pid)), f"{label}: the ledger shows DISPATCH")
c.done()
