"""Probe (round 5): scrap coming back of a batch-tracked item stands in its own batch's damaged bucket (around D-STK-46).

Ten of one batch in, six sold, two back as scrap naming the batch: the batch's row holds four on the shelf and two
damaged, and no row without a batch appears. A write-off naming the batch takes the two damaged first and leaves the
shelf at four; one naming no batch is refused or takes from the batch, and never leaves a row below nought."""
from _inv import *
from _flow import *
from _r3 import by_batch, iso

c = Check("p_scrap_return_batch")
w = World()
wh = w.warehouse()
p = w.product(goods_type="MEDICINE")
number = f"SB{w.tag}"
r = receive(w, wh["id"], p["id"], 10, batch=number, mfg=iso(w, -10), expiry=iso(w, 300))
c.eq(r.get("status", (0,))[0], 200, "ten of the batch received")
s = sell_and_dispatch(w, wh["id"], p["id"], 6)
c.eq(s.get("dispatch", (0,))[0], 200, "six dispatched")
note = must(w.admin.get(f"/api/v1/delivery-notes/{s['note']['id']}"), "note")
made = must(w.admin.post("/api/v1/sales-returns", {
    "customer_id": w.customer_id, "warehouse_id": wh["id"], "return_date": w.today,
    "lines": [{"source_document_type": "DELIVERY_NOTE", "source_document_id": note["id"],
               "source_document_line_id": note["lines"][0]["id"], "line_number": 1, "current_return_quantity": "2",
               "restock_quantity": "0", "damaged_quantity": "0", "scrap_quantity": "2", "batch_number": number,
               "warehouse_id": wh["id"]}]}), "return")
must(w.admin.post(f"/api/v1/sales-returns/{made['id']}/approve", {}), "approve return")
st, b = w.admin.post(f"/api/v1/sales-returns/{made['id']}/complete", {})
c.eq(st, 200, "two back as scrap: " + message(b)[:160])
c.eq(by_batch(w, p["id"]), {number: D(4)}, "four of the batch on the shelf, and no row without a batch")
c.eq(by_batch(w, p["id"], "damaged_quantity"), {number: D(2)}, "the two stand in the batch's damaged bucket")
batch_id = w.rows(p["id"])[0]["batch_id"]
base = {"branch_id": w.branch_id, "warehouse_id": wh["id"], "product_id": p["id"], "reason": "DAMAGE", "transaction_date": w.today}
st, b = w.admin.post(f"{INV}/write-offs", {**base, "quantity": "2", "batch_id": batch_id})
c.ok(st in (200, 201), "a write-off of two naming the batch", (st, message(b)[:200]))
c.eq((by_batch(w, p["id"]), by_batch(w, p["id"], "damaged_quantity")), ({number: D(4)}, {number: D(0)}),
     "took the damaged two and left the four on the shelf")
st, b = w.admin.post(f"{INV}/write-offs", {**base, "quantity": "1"})
rows = w.rows(p["id"])
c.ok(all(D(x[k]) >= 0 for x in rows for k in ("current_quantity", "damaged_quantity", "quarantine_quantity", "available_quantity")),
     "a write-off naming no batch leaves no row below nought", (st, message(b)[:160]))
total = sum(D(x["current_quantity"]) for x in rows)
c.ok((st in (409, 422) and total == D(4)) or (st in (200, 201) and total == D(3)),
     "it is refused with nothing moved, or takes one from the batch", (st, message(b)[:200], str(total)))
c.ok(st not in (200, 201) or all(x.get("batch_id") for x in rows if D(x["current_quantity"]) != 0 or True),
     "and makes no row without a batch", [(x.get("batch_number"), x["current_quantity"]) for x in rows])
c.done()
