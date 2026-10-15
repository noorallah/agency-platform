"""TC-MAST-033: a product always has a brand, and a brand a company (API half: brand/company refusals, product refusal, import Brand column checks, import keeps the spelt brand, update with blank Brand keeps it, Copy keeps it, deleting a brand in use is refused). The forms, the Lists sheet and the Unbranded filter are screen-only."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _mst import *
from _col import receipt, closing, position, journal
import re
from datetime import timedelta

IMP = "/api/v1/imports"

c = Check("tc_mast_033")
a = api()
t = tag()
nb = a.post(f"{PR}/brands", {"name": f"B33{t}"})
c.ok(nb[0] in (400, 422), "(a) a brand with no company is refused", f"{nb[0]} {message(nb[1])}")
co = must(a.post(f"{PR}/principals", {"code": f"C33{t}", "name": f"Company 33 {t}"}), "company")
br = must(a.post(f"{PR}/brands", {"name": f"B33{t}", "principal_id": co["id"]}), "brand")
c.eq(br.get("principal_id"), co["id"], "(b) the brand shows its company")
p = piece(a)
base = {"name": f"Brand check {t}", "product_type": "STOCK_ITEM", "tax_profile_group_code": "GST_18_LOCAL", "selling_price": "10", "base_uom_id": p, "inventory_uom_id": p, "sales_uom_id": p, "purchase_uom_id": p}
nobrand = a.post(PR, {"code": f"NB{t}", **base})
c.ok(nobrand[0] in (400, 422) and "brand" in message(nobrand[1]).lower(), "(c) a product with no brand is refused", f"{nobrand[0]} {message(nobrand[1])}")
c.eq(rows_of(a.get(f"{PR}?search=NB{t}")), [], "and nothing is saved")
made = must(a.post(PR, {"code": f"BC{t}", **base, "brand_id": br["id"]}), "(d) product with brand")
row = must(a.get(f"{PR}/{made['id']}"), "p")
c.eq((row["brand_id"], row["brand"]), (br["id"], f"B33{t}"), "(d) the product carries the brand")
head = ["Code", "Name", "Type", "Unit", "TaxGroup", "SellingPrice", "Brand"]
def f(rows):
    return csv_bytes([head, *rows])
r1 = [f"IA{t}", f"Import A {t}", "STOCK_ITEM", "PIECE", "GST_18_LOCAL", "10", f"b33{t}"]
r2 = [f"IB{t}", f"Import B {t}", "STOCK_ITEM", "PIECE", "GST_18_LOCAL", "10", ""]
r3 = [f"IC{t}", f"Import C {t}", "STOCK_ITEM", "PIECE", "GST_18_LOCAL", "10", "Nobody"]
ck = must(a.upload(f"{PR}/import-file", "p.csv", f([r1, r2, r3]), {"apply": "false", "existing": "refuse"}), "check")
by_row = {i["row"]: i for i in ck["issues"]}
c.ok(2 not in by_row, "(e) the b33 row has no problem", by_row.get(2))
c.ok(3 in by_row and by_row[3]["column"] == "Brand" and "is required" in by_row[3]["message"], "(e) the blank Brand is 'is required' on column Brand", by_row.get(3))
c.ok(4 in by_row and "not one of the firm's brands" in by_row[4]["message"], "(e) Nobody is 'not one of the firm's brands'", by_row.get(4))
c.eq(rows_of(a.get(f"{PR}?search=IA{t}")), [], "(e) a check writes nothing")
ap = must(a.upload(f"{PR}/import-file", "p.csv", f([r1]), {"apply": "true", "existing": "refuse"}), "apply")
c.eq(ap["imported"], True, "(f) the one-row file imports")
ia = [x for x in rows_of(a.get(f"{PR}?search=IA{t}")) if x["code"] == f"IA{t}"]
c.eq([x["brand"] for x in ia], [f"B33{t}"], "(f) the product has the brand, spelt as the brand is")
up = [f"BC{t}", f"Brand check {t}", "STOCK_ITEM", "PIECE", "GST_18_LOCAL", "55", ""]
ck2 = must(a.upload(f"{PR}/import-file", "p.csv", f([up]), {"apply": "true", "existing": "update"}), "update")
c.eq(ck2["imported"], True, f"(g) the update with a blank Brand is accepted {ck2['issues'][:1]}")
row = must(a.get(f"{PR}/{made['id']}"), "p")
c.eq((D(row["selling_price"]), row["brand"]), (D(55), f"B33{t}"), "(g) the price changes and the brand stays")
cp = a.post(f"{PR}/{made['id']}/duplicate", {})
c.ok(cp[0] in (200, 201), f"(h) Copy ({message(cp[1])})")
if cp[0] in (200, 201):
    c.eq(data(cp[1])["brand_id"], br["id"], "(h) the copy has brand B33")
dl = a.delete(f"{PR}/brands/{br['id']}")
c.ok(dl[0] in (409, 422) and "product" in message(dl[1]).lower(), "(i) deleting a brand in use is refused naming a product", f"{dl[0]} {message(dl[1])}")
c.done()
