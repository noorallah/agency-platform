"""Probe: stock and ledger export agree with the screens; spreadsheet formulas in names are neutralised."""
import csv
import io

from _inv import *

c = Check("p_export")
w = World()
a = w.warehouse()
p = w.product("EXP", name="=1+1 export probe")
w.stock_in(a["id"], p["id"], 7, 12)
other = w.product("EXQ")
w.stock_in(a["id"], other["id"], 3, 12)
E = f"{INV}/export"
st, raw = w.admin.raw(f"{E}?search={p['code']}")
c.eq(st, 200, "inventory csv exports")
rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
c.eq(len(rows) - 1, 1, "search narrows the export to the product's one row")
head = [h.lower() for h in rows[0]]
joined = ",".join(rows[1]) if len(rows) > 1 else ""
c.ok(other["code"] not in raw.decode(), "the other product is not in the file")
qi = next((i for i, h in enumerate(head) if "current" in h or h == "quantity"), None)
c.ok(qi is not None and D(rows[1][qi]) == D(7), "the quantity column reads 7", (rows[0], rows[1] if len(rows) > 1 else ""))
c.ok(not any(cell.startswith(("=", "+", "-", "@")) for cell in rows[1]) if len(rows) > 1 else False,
     "no cell starts with a formula character (the name was '=1+1 export probe')", rows[1] if len(rows) > 1 else "")
st, raw = w.admin.raw(f"{E}?dataset=ledger&search={p['code']}")
lrows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
c.eq((st, len(lrows) - 1), (200, 1), "the ledger export has the one opening movement")
c.ok(not any(cell.startswith(("=", "+", "@")) for r in lrows[1:] for cell in r), "ledger cells carry no formula characters")
st, raw = w.admin.raw(f"{E}?format=xlsx&search={p['code']}")
c.ok(st == 200 and raw[:2] == b"PK", "xlsx export is a workbook", (st, raw[:4]))
st, raw = w.admin.raw(f"{E}?dataset=ledger&format=xlsx&search={p['code']}")
c.ok(st == 200 and raw[:2] == b"PK", "xlsx ledger export is a workbook", (st, raw[:4]))
st, raw = w.admin.raw(f"{E}?format=pdf")
c.eq(st, 422, "an unknown format is a 422")
st, raw = client("viewer").raw(E)
c.eq(st, 403, "the read-only role holds no INVENTORY_EXPORT")
st, raw = client("store").raw(E)
c.eq(st, 200, "the store role exports")
c.done()
