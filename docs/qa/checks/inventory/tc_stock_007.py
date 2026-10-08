"""TC-STOCK-007 (API half): another firm's warehouse or product id in a filter answers an empty list, not an error."""
from _inv import *

c = Check("tc_stock_007")
s = state()
mine = client("platform_in_firm")
other = client("other_admin")
foreign_wh = data(other.get("/api/v1/warehouses?page_size=1")[1])[0]["id"]
foreign_p = data(other.get("/api/v1/products?page_size=1")[1])[0]["id"]
for name, query in (("warehouse", f"warehouse_id={foreign_wh}"), ("product", f"product_id={foreign_p}"),
                    ("branch", f"branch_id={data(other.get('/api/v1/branches')[1])[0]['id']}")):
    for path in ("", "/ledger", "/transactions"):
        st, b = mine.get(f"/api/v1/inventory{path}?{query}")
        c.ok(st == 200 and data(b) == [], f"{name} filter of another firm on /inventory{path or ''} is empty, not an error", (st, str(b)[:120]))
st, b = mine.get(f"/api/v1/batch-serial/batches/availability?product_id={foreign_p}&warehouse_id={foreign_wh}")
c.ok(st in (200, 404, 422), "availability for another firm's ids does not break", st)
c.ok(st != 200 or all(float(x.get("available_quantity", 0)) == 0 for x in (data(b) if isinstance(data(b), list) else [])),
     "and shows none of their stock")
c.done()
