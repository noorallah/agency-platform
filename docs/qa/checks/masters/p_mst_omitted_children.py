"""Probe: an update that omits a child collection leaves it alone; an explicit empty list clears it (customer addresses and contacts, vendor contacts)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _mst import *
from _col import receipt

c = Check("p_mst_omitted_children")
a = api()
d = described(a)
base = {"code": d["code"], "customer_type": "BUSINESS", "name": d["name"], "currency_code": "INR"}
st, body = a.put(f"{CU}/{d['id']}", {**base, "notes": "omitting children"})
c.eq(st, 200, f"update without addresses or contacts ({message(body)})")
row = must(a.get(f"{CU}/{d['id']}"), "row")
c.eq((len(row["addresses"]), len(row["contacts"])), (1, 1), "customer: omitted collections are left alone")
c.eq((D(row["credit_limit"]), row["payment_terms_days"]), (D(50000), 30), "and so are the terms")
st, body = a.put(f"{CU}/{d['id']}", {**base, "contacts": []})
c.eq(st, 200, f"explicit empty contacts ({message(body)})")
row = must(a.get(f"{CU}/{d['id']}"), "row")
c.eq((len(row["addresses"]), len(row["contacts"])), (1, 0), "customer: an explicit empty list clears that collection only")
v = vendor(a, contacts=[{"name": "C", "mobile": "+919800000001", "is_primary": True}], notes=[{"note": "n"}])
st, body = a.put(f"{VE}/{v['id']}", {"code": v["code"], "name": v["name"], "contacts": []})
c.eq(st, 200, f"vendor: explicit empty contacts ({message(body)})")
row = must(a.get(f"{VE}/{v['id']}"), "row")
c.eq((len(row["contacts"]), len(row["notes"])), (0, 1), "vendor: contacts cleared, notes left alone")
c.done()
