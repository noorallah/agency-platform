"""TC-STOCK-008: serial numbers received are AVAILABLE in their warehouse (warranty see F-note)."""
from _inv import *
from _flow import *

c = Check("tc_stock_008")
w = World()
wh = w.warehouse()
p = w.product(goods_type="ELECTRONICS")
sn = [f"S{w.tag}-{i:04d}" for i in range(1, 6)]
r = receive(w, wh["id"], p["id"], 5, serials=sn)
c.eq(r["status"][0], 200, "receipt with five serials completes")
rows = all_rows(w.admin, f"/api/v1/batch-serial/serials?product_id={p['id']}")
c.eq(sorted(x["serial_number"] for x in rows), sn, "five serials")
c.eq({x["status"] for x in rows}, {"AVAILABLE"}, "all AVAILABLE")
c.eq({x["warehouse_id"] for x in rows}, {wh["id"]}, "all in the receiving warehouse")
st, b = w.admin.get(f"/api/v1/batch-serial/serials?product_id={p['id']}&status=AVAILABLE&search={sn[0]}")
c.eq(len(data(b)), 1, "status filter keeps the match")
st, b = w.admin.get(f"/api/v1/batch-serial/serials/{rows[0]['id']}")
c.eq(st, 200, "detail opens")
# a receipt cannot carry warranty dates (case text wrong); they are set on the serial
st, b = w.admin.put(f"/api/v1/batch-serial/serials/{rows[0]['id']}",
                    {"warranty_start": w.today, "warranty_end": "2027-10-08"})
c.ok(st == 200, "warranty dates can be written on the serial", (st, message(b)))
if st == 200:
    c.eq((data(b)["warranty_start"], data(b)["warranty_end"]), (w.today, "2027-10-08"), "warranty round-trips")
c.done()
