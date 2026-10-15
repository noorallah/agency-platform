"""TC-CUST-002: place ids are the truth, the text is derived (API half; the picker loading each rung is screen-only)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _mst import *

c = Check("tc_cust_002")
a = api()
src = by_code(a, CU, one()["customer_code"])
full = must(a.get(f"{CU}/{src['id']}"), "fixture customer")
ad = full["addresses"][0]
t = tag()
body = {"code": f"G{t}", "name": f"Place Check {t}", "customer_type": "BUSINESS", "currency_code": "INR",
        "addresses": [{"address_type": "BILLING", "address_line1": "1 Road", "postal_code": "600001",
                       "city": "wrong city", "state": "wrong state", "country": "IN",
                       "country_id": ad["country_id"], "state_id": ad["state_id"],
                       "district_id": ad["district_id"], "city_id": ad["city_id"], "is_default_billing": True}]}
st, resp = a.post(CU, body)
c.eq(st, 201, f"create with the place ladder ({message(resp)})")
if st == 201:
    got = must(a.get(f"{CU}/{data(resp)['id']}"), "reread")["addresses"][0]
    c.eq((got["city_id"], got["state_id"], got["country_id"]), (ad["city_id"], ad["state_id"], ad["country_id"]), "ids held")
    c.eq((got["city"], got["state"], got["country"]), (ad["city"], ad["state"], "IN"), "text derived from the ids, not the typed text")
c.done()
