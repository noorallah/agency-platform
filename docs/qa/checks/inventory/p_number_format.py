"""Probe: every quantity the summaries return is written to four decimals, as the rows are."""
import re

from _inv import *
from _flow import *
import _flow

c = Check("p_number_format")
w = World()
wh = w.warehouse()
p = w.product()
w.vendor_id = _flow._vendor(w)
po = must(w.admin.post("/api/v1/purchases", {"branch_id": w.branch_id, "warehouse_id": wh["id"], "vendor_id": w.vendor_id, "purchase_date": w.today,
                                              "lines": [{"product_id": p["id"], "ordered_quantity": "10", "unit_price": "10"}]}), "po")
must(w.admin.post(f"/api/v1/purchases/{po['id']}/submit", {}), "s")
must(w.admin.post(f"/api/v1/purchases/{po['id']}/approve", {}), "a")
st, b = w.admin.get(f"{INV}/summary/by-product")
row = next(r for r in data(b) if r["scope_id"] == p["id"])
for k in ("current_quantity", "reserved_quantity", "available_quantity", "incoming_quantity", "outgoing_quantity", "projected_quantity"):
    c.ok(re.fullmatch(r"-?\d+(\.\d{4})?", str(row[k])) is not None, f"{k} is written like the other quantities (0 or 4 decimals)", row[k])
c.done()
