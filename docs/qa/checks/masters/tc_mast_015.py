"""TC-MAST-015: codes issued from a series (CUS, SUP, PRD; five digits; a typed code stands and the counter steps over it)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _mst import *
from _col import receipt, closing, position, journal
import re
from datetime import timedelta

IMP = "/api/v1/imports"

c = Check("tc_mast_015")
a = api()
t = tag()
def issue(path, body):
    r = a.post(path, body)
    c.eq(r[0], 201, f"blank code saves ({message(r[1])})")
    return data(r[1])["code"] if r[0] == 201 else ""
cu = lambda: issue(CU, {"name": f"Series customer {tag()}", "customer_type": "BUSINESS", "currency_code": "INR"})
ve = lambda: issue(VE, {"name": f"Series supplier {tag()}"})
p = piece(a)
pd = lambda: issue(PR, {"name": f"Series item {tag()}", "brand_id": check_brand(a), "product_type": "STOCK_ITEM", "tax_profile_group_code": "GST_18_LOCAL", "selling_price": "10", "base_uom_id": p, "inventory_uom_id": p, "sales_uom_id": p, "purchase_uom_id": p})
c1, v1, p1 = cu(), ve(), pd()
c.ok(re.fullmatch(r"CUS-\d{5}", c1) is not None, "customer code from the CUS series, five digits", c1)
c.ok(re.fullmatch(r"SUP-\d{5}", v1) is not None, "supplier code from the SUP series", v1)
c.ok(re.fullmatch(r"PRD-\d{5}", p1) is not None, "product code from the PRD series", p1)
n = int(c1.split("-")[1])
typed = f"CUS-{n + 2:05d}"
r = a.post(CU, {"code": typed, "name": f"Typed {t}", "customer_type": "BUSINESS", "currency_code": "INR"})
c.eq(r[0], 201, f"a typed code stands ({message(r[1])})")
c2 = cu()
c3 = cu()
c.eq(c2, f"CUS-{n + 1:05d}", "the next blank code is the next number")
c.eq(c3, f"CUS-{n + 3:05d}", "and the one after steps over the typed code")
c.done()
