"""TC-STOCK-013: expiry rules, shelf life and the issue rule on the product."""
from datetime import date, timedelta

from _inv import *
from _flow import *

c = Check("tc_stock_013")
w = World()
wh = w.warehouse()
d = date.fromisoformat(w.today)
iso = lambda n: (d + timedelta(days=n)).isoformat()
p = w.product(goods_type="MEDICINE", expiry_stop_sale_days=20, expiry_alert_days=45,
              expiry_return_days=60, shelf_life_days=365, issue_rule="FEFO")
c.eq((p["expiry_stop_sale_days"], p["expiry_alert_days"], p["expiry_return_days"], p["shelf_life_days"], p["issue_rule"]),
     (20, 45, 60, 365, "FEFO"), "product rules saved")
tag = w.tag
for name, days, qty in (("B3", 400, 10), ("B2", 15, 10), ("B4", 40, 10)):
    r = receive(w, wh["id"], p["id"], qty, batch=f"{name}-{tag}", expiry=iso(days), mfg=iso(days - 365))
    c.eq(r["status"][0], 200, f"{name} received")
# FEFO, B2 expires in 15 days which is inside the 20-day stop-sale window: B4 (40 days) goes first
s = sell_and_dispatch(w, wh["id"], p["id"], 3)
c.eq(s["dispatch"][0], 200, "dispatch ok")
left = {r["batch_number"]: D(r["current_quantity"]) for r in w.rows(p["id"])}
c.eq(left, {f"B3-{tag}": D(10), f"B2-{tag}": D(10), f"B4-{tag}": D(7)}, "stop-sale batch B2 skipped, FEFO took B4")
# returns due: B2 (15 days) and B4 (40) are inside 60; B3 (400) is not
st, b = w.admin.get("/api/v1/batch-serial/batches/returns-due")
due = {x["batch_number"]: x for x in data(b) if x["product_id"] == p["id"]}
c.eq(sorted(due), sorted([f"B2-{tag}", f"B4-{tag}"]), "monitor lists the batches inside the return window")
# shelf life: a manufacturing date only gives expiry = mfg + 365
r = receive(w, wh["id"], p["id"], 2, batch=f"M-{tag}", mfg=iso(-10))
c.eq(r["status"][0], 200, "receipt with only a manufacturing date")
st, b = w.admin.get(f"/api/v1/batch-serial/batches?product_id={p['id']}&search=M-{tag}")
got = data(b)
c.eq([x["expiry_date"] for x in got], [iso(-10 + 365)], "expiry = manufacturing date + 365")
# a typed expiry stands
r = receive(w, wh["id"], p["id"], 2, batch=f"T-{tag}", mfg=iso(-10), expiry=iso(200))
st, b = w.admin.get(f"/api/v1/batch-serial/batches?product_id={p['id']}&search=T-{tag}")
c.eq([x["expiry_date"] for x in data(b)], [iso(200)], "a typed expiry stands")
# FIFO: first received first, whatever the expiry (B3 was received first, B4 last)
st, b = w.update_product(p, issue_rule="FIFO")
c.eq(st, 200, "issue rule set to FIFO on the stocked product " + message(b))
before = {r["batch_number"]: D(r["current_quantity"]) for r in w.rows(p["id"])}
s = sell_and_dispatch(w, wh["id"], p["id"], 2)
after = {r["batch_number"]: D(r["current_quantity"]) for r in w.rows(p["id"])}
moved = {k: before[k] - after[k] for k in before if before[k] != after[k]}
c.eq(moved, {f"B3-{tag}": D(2)}, "FIFO issues from the batch received first (B3)")
# PICK: nothing is drawn silently
st, b = w.update_product(p, issue_rule="PICK")
c.eq(st, 200, "issue rule set to PICK " + message(b))
before = {r["batch_number"]: D(r["current_quantity"]) for r in w.rows(p["id"])}
s = sell_and_dispatch(w, wh["id"], p["id"], 1)
refused = [s.get(k, (0,))[0] for k in ("note_create", "note_approve", "dispatch")]
c.ok(any(x in (409, 422) for x in refused), "PICK without a chosen batch is refused", refused)
after = {r["batch_number"]: D(r["current_quantity"]) for r in w.rows(p["id"])}
c.eq(after, before, "nothing drawn silently")
# and with a chosen batch it dispatches
b4 = next(r for r in w.rows(p["id"]) if r["batch_number"] == f"B4-{tag}")
s = sell_and_dispatch(w, wh["id"], p["id"], 1, batches=[{"batch_id": b4["batch_id"], "quantity": "1"}])
c.eq(s.get("dispatch", (0,))[0], 200, "a picked batch dispatches " + str(s.get("note_create", ("", ""))[1])[:200])
c.done()
