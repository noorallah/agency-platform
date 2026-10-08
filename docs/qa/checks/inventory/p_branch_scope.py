"""Probe: a warehouse that belongs to another branch than the one named is refused; a transfer document may cross branches and records both."""
from _inv import *

c = Check("p_branch_scope")
w = World()
br = must(w.admin.post("/api/v1/branches", {"code": f"BR{w.tag}", "name": f"Branch {w.tag}"}), "branch")
wh2 = must(w.admin.post("/api/v1/warehouses", {"code": f"WB{w.tag}", "name": "wb", "branch_id": br["id"]}), "warehouse")
a = w.warehouse()
p = w.product()
w.stock_in(a["id"], p["id"], 10)
q = w.product()
base = {"transaction_date": w.today, "product_id": p["id"]}
for label, ans in (
    ("adjustment with the branch of another warehouse", w.admin.post(f"{INV}/adjustments", {**base, "branch_id": w.branch_id, "warehouse_id": wh2["id"], "quantity": "5", "reference_number": f"B1{w.tag}"})),
    ("opening stock with the branch of another warehouse", w.admin.post(f"{INV}/opening-stock", {"branch_id": w.branch_id, "warehouse_id": wh2["id"], "reference_number": f"B2{w.tag}", "posting_date": w.today, "lines": [{"product_id": p["id"], "quantity": "1", "unit_cost": "1"}]})),
    ("a count of a warehouse under the wrong branch", w.admin.post(f"{INV}/counts", {"branch_id": w.branch_id, "warehouse_id": wh2["id"], "count_date": w.today})),
    ("a repack in a warehouse under the wrong branch", w.admin.post(f"{INV}/repacks", {"repack_date": w.today, "branch_id": w.branch_id, "warehouse_id": wh2["id"], "lines": [{"kind": "CONSUME", "product_id": p["id"], "quantity": "1"}, {"kind": "PRODUCE", "product_id": w.product()["id"], "quantity": "1"}]})),
):
    c.ok(400 <= ans[0] < 500, f"{label} is refused", (ans[0], message(ans[1])[:70]))
t = must(w.admin.post(f"{INV}/stock-transfers", {"transfer_date": w.today, "from_warehouse_id": a["id"], "to_warehouse_id": wh2["id"], "lines": [{"product_id": p["id"], "quantity": "3"}]}), "doc")
c.ok(t["from_branch_id"] != t["to_branch_id"], "the document records both branches", (t["from_branch_id"], t["to_branch_id"]))
c.eq(w.admin.post(f"{INV}/stock-transfers/{t['id']}/dispatch", {})[0], 200, "dispatched across branches")
c.eq(w.admin.post(f"{INV}/stock-transfers/{t['id']}/receive", {"lines": [{"line_number": 1, "received_quantity": "3"}]})[0], 200, "received across branches")
rows = {r["warehouse_id"]: (r["branch_id"], D(r["current_quantity"])) for r in w.rows(p["id"])}
c.eq(rows.get(wh2["id"]), (br["id"], D(3)), "the destination row sits under the destination branch")
c.done()
