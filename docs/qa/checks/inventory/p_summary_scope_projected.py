"""Probe: incoming/outgoing/projected are carried to the branch and firm summaries (projected = available + incoming - outgoing)."""
from _inv import *
from _flow import *
import _flow

c = Check("p_summary_scope_projected")
w = World()
wh = w.warehouse()
p = w.product()
w.stock_in(wh["id"], p["id"], 5)
w.vendor_id = _flow._vendor(w)
po = must(w.admin.post("/api/v1/purchases", {"branch_id": w.branch_id, "warehouse_id": wh["id"], "vendor_id": w.vendor_id, "purchase_date": w.today,
                                              "lines": [{"product_id": p["id"], "ordered_quantity": "7", "unit_price": "10"}]}), "po")
must(w.admin.post(f"/api/v1/purchases/{po['id']}/submit", {}), "s")
must(w.admin.post(f"/api/v1/purchases/{po['id']}/approve", {}), "a")
for path, key in (("by-product", p["id"]), ("by-warehouse", wh["id"]), ("by-branch", w.branch_id), ("by-firm", w.firm_id)):
    st, b = w.admin.get(f"{INV}/summary/{path}")
    row = next((r for r in data(b) if r["scope_id"] == key), None)
    if not c.ok(row is not None, f"{path}: scope listed"):
        continue
    c.eq(D(row["projected_quantity"]), D(row["available_quantity"]) + D(row["incoming_quantity"]) - D(row["outgoing_quantity"]),
         f"{path}: projected = available + incoming - outgoing")
    if path in ("by-branch", "by-firm"):
        c.ok(D(row["incoming_quantity"]) >= 7, f"{path}: incoming includes the open order for 7", row["incoming_quantity"])
c.done()
