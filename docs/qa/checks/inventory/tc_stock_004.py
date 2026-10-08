"""TC-STOCK-004: a physical count posts only what was counted."""
from _inv import *
from _flow import *

c = Check("tc_stock_004")
w = World()
wh = w.warehouse()
p, q = w.product(), w.product()
w.stock_in(wh["id"], p["id"], 50)
w.stock_in(wh["id"], q["id"], 5)
st, b = w.admin.post(f"{INV}/counts", {"branch_id": w.branch_id, "warehouse_id": wh["id"], "count_date": w.today})
c.eq(st, 201, "count opened")
cnt = data(b)
c.eq(len(cnt["lines"]), 2, "one line per product in the warehouse")
c.eq(sorted(D(l["expected_quantity"]) for l in cnt["lines"]), [D(5), D(50)], "expected quantities")
lines = [{"product_id": l["product_id"], "counted_quantity": "49" if l["product_id"] == p["id"] else None}
         for l in cnt["lines"]]
st, b = w.admin.put(f"{INV}/counts/{cnt['id']}", {"lines": lines})
c.eq(st, 200, "progress saved")
st, b = w.admin.post(f"{INV}/counts/{cnt['id']}/post", {})
c.eq(st, 200, "count posted")
done = data(b)
c.eq(done["status"], "POSTED", "status POSTED")
mine = [l for l in done["lines"] if l["product_id"] == p["id"]][0]
c.eq(D(mine["variance_quantity"]), D(-1), "variance -1")
c.eq(w.qty(p["id"]), D(49), "counted product at 49")
c.eq(w.qty(q["id"]), D(5), "uncounted product untouched")
led = w.ledger(p["id"])
adj = [x for x in led if x["transaction_type"] == "ADJUSTMENT"]
c.eq([(D(x["current_quantity_delta"]), x["reference_number"]) for x in adj], [(D(-1), done["count_number"])],
     "one ADJUSTMENT of -1 naming the count")
c.eq([x for x in w.ledger(q["id"]) if x["transaction_type"] == "ADJUSTMENT"], [], "no movement for the uncounted line")
js = entries(w, done["count_number"])
c.eq(len(js), 1, "one journal for the count")
if js:
    net = by_purpose(w, js[0])
    c.eq(net.get("INVENTORY_ADJUSTMENT"), D(60), "Dr adjustment 60 (loss of 1 at cost)")
st, b = w.admin.put(f"{INV}/counts/{cnt['id']}", {"lines": lines})
c.ok(st in (409, 422), "a posted count cannot be edited", (st, message(b)))
st, b = w.admin.post(f"{INV}/counts/{cnt['id']}/post", {})
c.ok(st in (409, 422), "a posted count cannot be posted twice", (st, message(b)))
c.eq(w.qty(p["id"]), D(49), "still 49 after the refused second post")
c.done()
