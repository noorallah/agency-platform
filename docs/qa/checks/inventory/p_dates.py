"""Probe: a movement dated in the future or in a closed/unopened year is refused on every stock write, not only on those that post a journal."""
from _inv import *

c = Check("p_dates")
w = World()
a, b2 = w.warehouse(), w.warehouse()
p = w.product()
w.stock_in(a["id"], p["id"], 20)
for label, dt in (("future", "2030-01-01"), ("a year with no open period", "1999-01-01")):
    base = {"branch_id": w.branch_id, "product_id": p["id"], "transaction_date": dt}
    n = suffix(4)
    for what, ans in (
        ("write-off", w.admin.post(f"{INV}/write-offs", {**base, "warehouse_id": a["id"], "quantity": "1", "reason": "DAMAGE", "reference_number": f"D1{n}"})),
        ("transfer", w.admin.post(f"{INV}/transfers", {**base, "from_warehouse_id": a["id"], "to_warehouse_id": b2["id"], "quantity": "1", "reference_number": f"D2{n}"})),
        ("quarantine hold", w.admin.post(f"{INV}/quarantine", {**base, "warehouse_id": a["id"], "action": "HOLD", "quantity": "1", "reference_number": f"D3{n}"})),
        ("stock-transfer document", w.admin.post(f"{INV}/stock-transfers", {"transfer_date": dt, "from_warehouse_id": a["id"], "to_warehouse_id": b2["id"], "lines": [{"product_id": p["id"], "quantity": "1"}]})),
        ("count", w.admin.post(f"{INV}/counts", {"branch_id": w.branch_id, "warehouse_id": a["id"], "count_date": dt})),
        ("repack", w.admin.post(f"{INV}/repacks", {"repack_date": dt, "branch_id": w.branch_id, "warehouse_id": a["id"], "lines": [{"kind": "CONSUME", "product_id": p["id"], "quantity": "1"}, {"kind": "PRODUCE", "product_id": w.product()["id"], "quantity": "1"}]})),
    ):
        c.ok(400 <= ans[0] < 500, f"{what} dated {label} is refused", (ans[0], message(ans[1])[:70]))
c.done()
