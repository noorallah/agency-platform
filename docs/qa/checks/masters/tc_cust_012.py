"""TC-CUST-012: two parties of one name are told apart by area and city (API half: the rows carry the area and city the pickers and the Area, city column read; the pickers themselves are screen-only)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _mst import *
from _col import receipt, closing, position, journal

c = Check("tc_cust_012")
a = api()
t = tag()
name = f"Sri Balaji Medicals {t}"
def addr(area: str, city: str) -> dict:
    return {"address_type": "BILLING", "address_line1": f"1 {area}", "area": area, "city": city,
            "state": "Telangana", "country": "IN", "postal_code": "500001", "is_default_billing": True}
c1 = must(a.post(CU, {"code": f"BA{t}", "name": name, "customer_type": "BUSINESS", "currency_code": "INR", "addresses": [addr("Abids", "Hyderabad")]}), "c1")
c2 = must(a.post(CU, {"code": f"BB{t}", "name": name, "customer_type": "BUSINESS", "currency_code": "INR", "addresses": [addr("Kavadiguda", "Secunderabad")]}), "c2")
rows = rows_of(a.get(f"{CU}?search=Sri%20Balaji%20Medicals%20{t}&page_size=20"))
places = sorted((r["code"], r["addresses"][0]["area"], r["addresses"][0]["city"]) for r in rows)
c.eq(places, [(f"BA{t}", "Abids", "Hyderabad"), (f"BB{t}", "Kavadiguda", "Secunderabad")], "search finds both, each with its own area and city")
one_ = one()
src = by_code(a, CU, one_["customer_code"])
ad = must(a.get(f"{CU}/{src['id']}"), "src")["addresses"][0]
sup_name = f"Sri Balaji Agencies {t}"
v1 = must(a.post(VE, {"code": f"SA{t}", "name": sup_name, "addresses": [{"address_type": "OFFICE", "address_line1": "1 Road", "country_id": ad["country_id"], "state_id": ad["state_id"], "district_id": ad["district_id"], "city_id": ad["city_id"], "is_primary": True}]}), "v1")
v3 = must(a.post(VE, {"code": f"SC{t}", "name": sup_name}), "v3")
rows = {r["code"]: r for r in rows_of(a.get(f"{VE}?search={t}&page_size=20"))}
c.eq(len(rows), 2, "search finds both suppliers")
c.eq(rows[f"SA{t}"]["addresses"][0].get("city"), ad["city"], "placed supplier: city from the place ladder")
c.eq(rows[f"SC{t}"]["addresses"], [], "unplaced supplier: no address, blank column")
c.done()
