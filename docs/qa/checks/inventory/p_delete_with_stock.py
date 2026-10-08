"""Probe: a batch, a serial number or an inventory row that still holds stock cannot be deleted."""
from datetime import date, timedelta

from _inv import *
from _flow import *

c = Check("p_delete_with_stock")
w = World()
wh = w.warehouse()
d = date.fromisoformat(w.today)
iso = lambda n: (d + timedelta(days=n)).isoformat()
pb, ps, p = w.product(goods_type="MEDICINE"), w.product(goods_type="ELECTRONICS"), w.product()
receive(w, wh["id"], pb["id"], 5, batch=f"DB{w.tag}", mfg=iso(-1), expiry=iso(200))
sn = [f"DS{w.tag}1", f"DS{w.tag}2"]
receive(w, wh["id"], ps["id"], 2, serials=sn)
w.stock_in(wh["id"], p["id"], 3)
bid = next(r["batch_id"] for r in w.rows(pb["id"]) if r["batch_number"] == f"DB{w.tag}")
st, b = w.admin.delete(f"/api/v1/batch-serial/batches/{bid}")
c.ok(st in (409, 422), "a batch holding 5 units cannot be deleted", (st, message(b)))
rows = all_rows(w.admin, f"/api/v1/batch-serial/serials?product_id={ps['id']}")
st, b = w.admin.delete(f"/api/v1/batch-serial/serials/{rows[0]['id']}")
c.ok(st in (409, 422), "an AVAILABLE serial number in stock cannot be deleted", (st, message(b)))
st, b = w.admin.delete(f"{INV}/{w.rows(p['id'])[0]['id']}")
c.eq(st, 422, "an inventory row with stock cannot be deleted")
st, b = w.admin.delete(f"/api/v1/warehouses/{wh['id']}")
c.ok(st in (409, 422), "a warehouse holding stock cannot be deleted", (st, message(b)))
c.eq(w.qty(pb["id"]), D(5), "the batch stock is still 5")
st, b = w.admin.get(f"/api/v1/batch-serial/batches?product_id={pb['id']}")
c.eq(len(data(b)), 1, "and its batch is still listed")
c.done()
