"""Probe: stock levels (minimum, maximum, reorder, safety) refuse nonsense; an inventory row keeps its own figures when only levels change."""
from _inv import *

c = Check("p_levels")
w = World()
a = w.warehouse()
p = w.product()
w.stock_in(a["id"], p["id"], 10)
row = w.rows(p["id"])[0]
key = {"branch_id": w.branch_id, "warehouse_id": a["id"], "product_id": p["id"]}
ok = w.admin.put(f"{INV}/{row['id']}", {**key, "minimum_level": "2", "maximum_level": "50", "reorder_level": "5", "safety_stock": "1"})
c.eq(ok[0], 200, "sane levels save")
c.eq(D(data(ok[1])["current_quantity"]), D(10), "saving levels leaves the quantity alone")
for label, patch in (("minimum above maximum", {"minimum_level": "60", "maximum_level": "50"}),
                     ("negative reorder level", {"reorder_level": "-1"}),
                     ("negative safety stock", {"safety_stock": "-3"}),
                     ("reorder level above maximum", {"reorder_level": "80", "maximum_level": "50"})):
    st, b = w.admin.put(f"{INV}/{row['id']}", {**key, **patch})
    c.ok(400 <= st < 500, f"{label} is refused", (st, message(b)))
# an update cannot move the row to another product
other = w.product()
st, b = w.admin.put(f"{INV}/{row['id']}", {**key, "product_id": other["id"]})
c.ok(400 <= st < 500, "an inventory row cannot be re-pointed at another product", (st, message(b)))
c.eq(w.qty(p["id"]), D(10), "the stock stayed on its product")
# nor to another warehouse: that would be a transfer with no movement, no ledger row and no cost
b2 = w.warehouse()
st, b = w.admin.put(f"{INV}/{row['id']}", {**key, "warehouse_id": b2["id"]})
c.ok(400 <= st < 500, "an inventory row cannot be re-pointed at another warehouse", (st, message(b)))
c.eq(w.qty(p["id"], a["id"]), D(10), "the stock stayed in its warehouse")
# a row for the same place twice
st, b = w.admin.post(INV, key)
c.ok(st in (200, 201, 409), "creating the row that exists answers sanely", (st, message(b)))
rows = w.rows(p["id"])
c.eq(len(rows), 1, "still one row for the product in the warehouse")
c.done()
