"""TC-CUST-006: segments: assigning one, and refusing to delete one in use."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _mst import *
from _col import receipt, closing, position, journal

c = Check("tc_cust_006")
a = api()
t = tag()
g1 = must(a.post(f"{CU}/groups", {"code": f"S1{t}", "name": f"Retailer {t}", "default_discount_percent": "1.75"}), "group 1")
g2 = must(a.post(f"{CU}/groups", {"code": f"S2{t}", "name": f"Wholesaler {t}", "default_discount_percent": "3.25"}), "group 2")
d = described(a, customer_group_id=g1["id"])
st, body = a.put(f"{CU}/{d['id']}", {"code": d["code"], "customer_type": "BUSINESS", "name": d["name"], "currency_code": "INR", "customer_group_id": g2["id"]})
c.eq(st, 200, f"segment changed ({message(body)})")
c.eq(must(a.get(f"{CU}/{d['id']}"), "reread")["customer_group_id"], g2["id"], "segment holds")
r = a.delete(f"{CU}/groups/{g2['id']}")
c.ok(r[0] in (409, 422) and "still in" in message(r[1]), "deleting a segment in use is refused naming the count", f"{r[0]} {message(r[1])}")
c.eq(a.delete(f"{CU}/groups/{g1['id']}")[0], 200, "an unused segment can go")
c.eq(must(a.get(f"{CU}/{d['id']}"), "reread")["customer_group_id"], g2["id"], "refusal left the customer on its segment")
c.done()
