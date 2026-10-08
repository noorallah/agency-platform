"""TC-STOCK-005: dispatch draws the earliest-expiring batch that has not expired."""
from datetime import date, timedelta

from _inv import *
from _flow import *

c = Check("tc_stock_005")
w = World()
wh = w.warehouse()
p = w.product(goods_type="MEDICINE")
d = date.fromisoformat(w.today)
iso = lambda n: (d + timedelta(days=n)).isoformat()
for name, days in (("B1", -30), ("B2", 20), ("B3", 400)):
    r = receive(w, wh["id"], p["id"], 10, batch=f"{name}-{w.tag}", expiry=iso(days), mfg=iso(days - 365))
    c.eq(r["status"][0], 200, f"batch {name} received")
st, b = w.admin.get(f"/api/v1/batch-serial/batches?product_id={p['id']}")
c.eq(len(data(b)), 3, "three batches")
c.eq(sorted(D(x["available_quantity"]) for x in data(b)), [D(10)] * 3, "10 available in each")
s = sell_and_dispatch(w, wh["id"], p["id"], 5)
c.eq(s["dispatch"][0], 200, "dispatched")
by_batch = {r["batch_number"]: D(r["current_quantity"]) for r in w.rows(p["id"])}
c.eq(by_batch.get(f"B2-{w.tag}"), D(5), "5 came from B2, the earliest unexpired")
c.eq(by_batch.get(f"B1-{w.tag}"), D(10), "expired B1 untouched")
c.eq(by_batch.get(f"B3-{w.tag}"), D(10), "B3 untouched")
disp = [x for x in w.ledger(p["id"]) if x["transaction_type"] == "DISPATCH"]
c.eq([(D(x["quantity"]), x["batch_number"]) for x in disp], [(D(5), f"B2-{w.tag}")], "DISPATCH 5 on B2 naming the note")
st, b = w.admin.get("/api/v1/batch-serial/batches/expiry-dashboard")
c.ok(st == 200 and b["data"]["total_expired"] >= 1, "dashboard counts an expired batch", b)
c.done()
