"""TC-SELL-108: orders approved together say what stays on back order (the report and bulk path)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sell import *

c = Check("tc_sell_108")
a = admin()
sc = Scene(a, stock="100")               # the product in stock
empty = sc.new_product("NS", "100", "0", "GST_18_LOCAL")   # no stock
o_in = new_order(sc, "3")
o_ten = new_order(sc, "10", product=empty)
o_seven = new_order(sc, "7", product=empty)
ids = [o["id"] for o in (o_in, o_ten, o_seven)]
bulk = a.post(f"{SO}/bulk-approve", {"items": [{"id": i} for i in ids]})
c.eq(bulk[0], 200, f"step 1: bulk approve answers ({message(bulk[1])})")
res = data(bulk[1])
rows = res["results"]
c.eq((res["done"], res["refused"]), (3, 0), "step 1: Approved 3 of 3")
back = rows_of(a.get(f"{SO}/reports/back-orders?" + "&".join(f"order_id={i}" for i in ids)))
named = {(r["order_number"], r["product_code"]): r for r in back}
c.eq(sorted(r["order_id"] for r in back), sorted([o_ten["id"], o_seven["id"]]), "step 1: only the two short orders are named")
c.eq(sorted(D(r["requested_quantity"]) for r in back), [D(7), D(10)], "step 1: 10 of 10 and 7 of 7")
whole = rows_of(a.get(f"{SO}/reports/back-orders"))
for r in back:
    mine = [w for w in whole if w["line_id"] == r["line_id"]]
    c.ok(mine and mine[0] == r, "the id-scoped row equals its row of the whole report", r["order_number"])
lone = new_order(sc, "4", product=empty)
one = must(a.post(f"{SO}/{lone['id']}/approve", {}), "step 2: single approve")
c.eq(one["status"], "APPROVED", "step 2: the order is approved")
only = rows_of(a.get(f"{SO}/reports/back-orders?order_id={lone['id']}"))
c.eq([D(r["requested_quantity"]) for r in only], [D(4)], "step 2: the warning names what is short on that order alone")
many = a.get(f"{SO}/reports/back-orders?" + "&".join(f"order_id={i}" for i in [ids[0]] * 201))
c.eq(many[0], 422, "201 ids is a 422")
c.eq(len(rows_of(a.get(f"{SO}/reports/back-orders?" + "&".join(f"order_id={i}" for i in [ids[0]] * 200)))), 0, "200 ids is allowed")
c.done()
