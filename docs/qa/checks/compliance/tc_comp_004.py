"""TC-COMP-004: the e-invoice list shows sandbox references only (firm one). The banner is screen-only."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _comp import *

c = Check("tc_comp_004")
a = api()
f = firm()
rows = rows_of(a.get(f"{EINV}/registrations?page_size=100"))
mine = [x for x in rows if x["sales_invoice_id"] in (f["invoices"]["A"], f["invoices"]["B"])]
c.eq(len(mine), 2, "A and B are registered")
c.eq(sorted(x["sales_invoice_id"] for x in mine), sorted([f["invoices"]["A"], f["invoices"]["B"]]), "they are A and B")
for x in rows:
    c.ok(str(x["irn"]).startswith("SBX"), "reference marked SBX", x["irn"])
    c.eq((x["mode"], x["status"]), ("SANDBOX", "REGISTERED"), "mode SANDBOX, status REGISTERED")
    c.ok("LIVE" not in (x["mode"], x["provider"]), "nothing reads LIVE")
for x in mine:
    c.eq(data(a.get(f"{EINV}/invoices/{x['sales_invoice_id']}/eway-bill")[1]), None, "no e-way bill yet")
c.done()
