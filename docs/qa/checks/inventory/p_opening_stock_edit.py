"""Probe: a draft opening-stock batch can be edited (lines replaced) and then posted; the posted batch cannot be edited."""
from _inv import *

c = Check("p_opening_stock_edit")
w = World()
a = w.warehouse()
p = w.product()
os_ = must(w.admin.post(f"{INV}/opening-stock", {"branch_id": w.branch_id, "warehouse_id": a["id"], "reference_number": f"E{w.tag}", "posting_date": w.today,
                                                "lines": [{"product_id": p["id"], "quantity": "1", "unit_cost": "5"}]}), "draft")
body = {"branch_id": w.branch_id, "warehouse_id": a["id"], "reference_number": f"E{w.tag}", "posting_date": w.today,
        "lines": [{"product_id": p["id"], "quantity": "2", "unit_cost": "5"}]}
st, b = w.admin.put(f"{INV}/opening-stock/{os_['id']}", body)
c.eq(st, 200, "a draft batch is edited (quantity 1 to 2): " + message(b))
if st == 200:
    c.eq(D(data(b)["lines"][0]["quantity"]), D(2), "the new line is kept")
    st, b = w.admin.post(f"{INV}/opening-stock/{os_['id']}/post", {})
    c.eq(st, 200, "and posted")
    c.eq(w.qty(p["id"]), D(2), "2 on hand")
    st, b = w.admin.put(f"{INV}/opening-stock/{os_['id']}", body)
    c.eq(st, 422, "a posted batch cannot be edited")
c.done()
