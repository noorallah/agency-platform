"""Probe: a file import with one bad row writes nothing, on customers, suppliers and products, and the check beforehand writes nothing either."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _mst import *
from _col import receipt

c = Check("p_mst_import_bad_row")
a = api()
t = tag()
p = "PIECE"
cases = {
    CU: ([["Code", "Name", "Type"], [f"IX1{t}", f"Good one {t}", "BUSINESS"], [f"IX2{t}", f"Bad type {t}", "NOT-A-TYPE"], [f"IX3{t}", f"Good two {t}", "BUSINESS"]], {"existing": "refuse"}, f"IX"),
    VE: ([["Code", "Name", "Status"], [f"IV1{t}", f"Good one {t}", "ACTIVE"], [f"IV2{t}", f"Bad status {t}", "NOT-A-STATUS"], [f"IV3{t}", f"Good two {t}", "ACTIVE"]], {"existing": "refuse"}, f"IV"),
    PR: ([["Code", "Name", "Type", "Unit", "TaxGroup", "SellingPrice", "Brand"],
          [f"IP1{t}", f"Good one {t}", "STOCK_ITEM", p, "GST_18_LOCAL", "10", "Check Brand"],
          [f"IP2{t}", f"Bad unit {t}", "STOCK_ITEM", "NO-SUCH-UNIT", "GST_18_LOCAL", "10", "Check Brand"],
          [f"IP3{t}", f"Good two {t}", "STOCK_ITEM", p, "GST_18_LOCAL", "10", "Check Brand"]], {"existing": "refuse"}, f"IP"),
}
check_brand(a)
for path, (rows, form, prefix) in cases.items():
    f = csv_bytes(rows)
    ck = a.upload(f"{path}/import-file", "x.csv", f, {**form, "apply": "false"})
    c.eq(ck[0], 200, f"{path}: check answers ({message(ck[1])})")
    if ck[0] == 200:
        c.ok(any(i["row"] == 3 for i in data(ck[1])["issues"]), f"{path}: the check names row 3", data(ck[1])["issues"])
    c.eq(rows_of(a.get(f"{path}?search={prefix}1{t}")), [], f"{path}: the check wrote nothing")
    ap = a.upload(f"{path}/import-file", "x.csv", f, {**form, "apply": "true"})
    c.eq(data(ap[1])["imported"] if ap[0] == 200 else ap[0], False, f"{path}: apply with a bad row imports nothing")
    c.eq(rows_of(a.get(f"{path}?search={prefix}1{t}")) + rows_of(a.get(f"{path}?search={prefix}3{t}")), [], f"{path}: neither good row was written")
c.done()
