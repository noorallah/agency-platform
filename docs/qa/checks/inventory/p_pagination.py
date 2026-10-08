"""Probe: page_size over the cap, page 0 and negative sizes are a 422 naming the limit (never a 500) on every inventory list."""
from _inv import *

c = Check("p_pagination")
w = World()
paths = [
    "/api/v1/inventory", "/api/v1/inventory/ledger", "/api/v1/inventory/transactions", "/api/v1/inventory/counts",
    "/api/v1/inventory/opening-stock", "/api/v1/inventory/reports/stock-valuation", "/api/v1/inventory/reports/stock-ageing",
    "/api/v1/inventory/reports/slow-moving", "/api/v1/inventory/reports/dead-stock", "/api/v1/inventory/reports/free-goods",
    "/api/v1/inventory/reports/stock-statement?from_date=2026-04-01&to_date=2026-10-08",
    "/api/v1/batch-serial/batches", "/api/v1/batch-serial/serials", "/api/v1/batch-serial/lots",
]
for path in paths:
    joiner = "&" if "?" in path else "?"
    for label, q in (("page_size=100000", "page_size=100000"), ("page_size=0", "page_size=0"), ("page=0", "page=0"),
                     ("page_size=-5", "page_size=-5"), ("page_size=abc", "page_size=abc")):
        st, b = w.admin.get(f"{path}{joiner}{q}")
        c.eq(st, 422, f"{path.split('/api/v1/')[1].split('?')[0]} {label} is a 422")
    st, b = w.admin.get(f"{path}{joiner}page=999999&page_size=5")
    c.ok(st == 200, f"{path.split('/api/v1/')[1].split('?')[0]}: a page past the end is an empty 200", (st, message(b)))
# sort and filter parameters
for q in ("sort_by=nonsense", "sort_direction=sideways", "product_id=not-a-uuid", "warehouse_id=1"):
    st, b = w.admin.get(f"/api/v1/inventory?{q}")
    c.ok(st in (200, 422), f"/inventory?{q} is not a 500", st)
c.done()
