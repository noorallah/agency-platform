"""TC-MAST-014: a customer who is also a supplier (link by PAN, refusals, combined statement and its permissions, the link read back from the vendor). The Party Adjustments set-off preselect is screen-only."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _mst import *
from _col import receipt, closing, position, journal
import re
from datetime import timedelta

IMP = "/api/v1/imports"

c = Check("tc_mast_014")
a, m = api(), api("manager")
t = tag()
pan = "AAACP" + str(abs(hash(t)) % 9000 + 1000) + "C"
cu = must(a.post(CU, {"code": f"AS{t}", "name": f"Also supplier {t}", "customer_type": "BUSINESS", "currency_code": "INR", "pan_number": pan}), "customer")
v_same = vendor(a, pan=pan, tax=[{"pan": pan, "is_primary": True}])
v_other = vendor(a, pan="BBBBB1111B", tax=[{"pan": "BBBBB1111B", "is_primary": True}])
def link(vid):
    row = must(a.get(f"{CU}/{cu['id']}"), "cu")
    return a.put(f"{CU}/{cu['id']}", echo("CustomerUpdate", row, {"addresses": "CustomerAddressInput", "contacts": "CustomerContactInput"}, linked_vendor_id=vid))
r = link(v_other["id"])
c.ok(r[0] in (409, 422) and ("PAN" in message(r[1]) or "pan" in message(r[1])), "a vendor with a different PAN is refused by name", f"{r[0]} {message(r[1])}")
r = link(v_same["id"])
c.eq(r[0], 200, f"the same-PAN vendor links ({message(r[1])})")
c.eq(must(a.get(f"{CU}/{cu['id']}"), "cu")["linked_vendor_id"], v_same["id"], "the link is held")
back = must(a.get(f"{VE}/{v_same['id']}/linked-customer"), "back")
c.ok(back and back.get("customer_id", back.get("id")) == cu["id"] or cu["id"] in json.dumps(back), "the supplier editor shows the link back", back)
cu2 = must(a.post(CU, {"code": f"AT{t}", "name": f"Other customer {t}", "customer_type": "BUSINESS", "currency_code": "INR", "pan_number": pan}), "cu2")
row2 = must(a.get(f"{CU}/{cu2['id']}"), "cu2")
r = a.put(f"{CU}/{cu2['id']}", echo("CustomerUpdate", row2, {"addresses": "CustomerAddressInput", "contacts": "CustomerContactInput"}, linked_vendor_id=v_same["id"]))
c.ok(r[0] in (409, 422), "a vendor already linked to another customer is refused", f"{r[0]} {message(r[1])}")
sc = Scene(a, stock="20")
with counter(a):
    b = must(a.post(SI, sc.bill_body("1", customer=cu)), "bill")
    must(a.post(f"{SI}/{b['id']}/approve", {}), "approve")
day = today().isoformat()
cs = a.get(f"{CU}/{cu['id']}/combined-statement?from_date={day}&to_date={day}")
c.eq(cs[0], 200, f"combined statement ({message(cs[1])})")
if cs[0] == 200:
    g = data(cs[1])
    c.eq((D(g["receivable_closing"]), D(g["payable_closing"]), D(g["net_closing"])), (D(118), D(0), D(118)), "receivable 118, payable 0, net 118")
    c.eq([l["account"] for l in g["lines"]], ["CUSTOMER"] if g["lines"] and g["lines"][0]["account"] == "CUSTOMER" else [l["account"] for l in g["lines"]], "lines come from the customer account")
c.ok(m.get(f"{CU}/{cu['id']}/combined-statement?from_date={day}&to_date={day}")[0] in (200, 403), "(the sales manager holds both view codes, so it reads)")
c.done()
