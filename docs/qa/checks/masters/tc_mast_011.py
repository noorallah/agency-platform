"""TC-MAST-011: principals and brands, and a price revision with an effective date (API half: master rows, the product carries the brand, dated revisions resolve through the unit-price resolver, the revision import checks every row). The sales-analysis screen is not driven."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _mst import *
from _col import receipt, closing, position, journal
import re
from datetime import timedelta

IMP = "/api/v1/imports"

c = Check("tc_mast_011")
a = api()
t = tag()
pr = must(a.post(f"{PR}/principals", {"code": f"AF{t}", "name": f"Acme Foods {t}"}), "principal")
br = must(a.post(f"{PR}/brands", {"name": f"Acme Gold {t}", "principal_id": pr["id"]}), "brand")
p = product(a, brand_id=br["id"])
c.eq(must(a.get(f"{PR}/{p['id']}"), "p")["brand"], f"Acme Gold {t}", "the product carries the brand")
day = today()
yest, nextw = day - timedelta(days=1), day + timedelta(days=7)
from datetime import timedelta
back = a.post(f"{PR}/{p['id']}/price-revisions", {"effective_from": yest.isoformat(), "selling_price": "99"})
c.ok(back[0] == 422 and "not from" in message(back[1]), "a revision dated yesterday is refused (the case says one is added)", f"{back[0]} {message(back[1])}")
r1 = a.post(f"{PR}/{p['id']}/price-revisions", {"effective_from": day.isoformat(), "selling_price": "120"})
c.eq(r1[0], 201, f"today's revision ({message(r1[1])})")
r2 = a.post(f"{PR}/{p['id']}/price-revisions", {"effective_from": nextw.isoformat(), "selling_price": "150"})
c.eq(r2[0], 201, f"next week's revision ({message(r2[1])})")
def price_on(d):
    got = must(a.get(f"/api/v1/price-levels/unit-prices?product_ids={p['id']}&on={d.isoformat()}"), "prices")
    return D(got["prices"][0]["unit_price"])
c.eq(price_on(day), D(120), "a quote today takes today's revision")
c.eq(price_on(nextw), D(150), "a quote dated next week takes the later one")
c.eq(price_on(yest), D(100), "dated before any revision the product's own price stands")
c.eq(D(must(a.get(f"{PR}/{p['id']}"), "p")["selling_price_in_force"]), D(120), "the product reads the price in force today")
rows = [["Code", "EffectiveFrom", "SellingPrice"], [p["code"], (day + timedelta(days=14)).strftime("%d-%m-%Y"), "175"], ["NO-SUCH-" + t, (day + timedelta(days=14)).strftime("%d-%m-%Y"), "10"]]
ck = must(a.upload(f"{PR}/price-revisions/import-file", "rev.csv", csv_bytes(rows), {"apply": "false"}), "check")
c.ok(len(ck["issues"]) == 1 and ck["issues"][0]["row"] == 3, "the check names the bad row", ck["issues"])
ap = a.upload(f"{PR}/price-revisions/import-file", "rev.csv", csv_bytes(rows), {"apply": "true"})
c.eq(data(ap[1])["imported"] if ap[0] == 200 else None, False, "applying a file with one bad row imports nothing")
c.eq(len(rows_of(a.get(f"{PR}/{p['id']}/price-revisions"))), 2, "still two revisions")
c.done()
