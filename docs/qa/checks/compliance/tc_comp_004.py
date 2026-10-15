"""TC-COMP-004: the e-invoice list shows sandbox references only (firm one). The banner is screen-only."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _comp import *

c = Check("tc_comp_004")
a = api()
f = firm()
rows = rows_of(a.get(f"{EINV}/registrations?page_size=100"))
c.eq(len(rows), 2, "two registrations (A and B)")
c.eq(sorted(x["invoice_number"] for x in rows), ["SI-26-27-000001", "SI-26-27-000002"], "they are A and B")
for x in rows:
    c.ok(str(x["irn"]).startswith("SBX"), "reference marked SBX", x["irn"])
    c.eq((x["mode"], x["status"]), ("SANDBOX", "REGISTERED"), "mode SANDBOX, status REGISTERED")
    c.ok("LIVE" not in (x["mode"], x["provider"]), "nothing reads LIVE")
    c.eq(data(a.get(f"{EINV}/invoices/{x['sales_invoice_id']}/eway-bill")[1]), None, "no e-way bill yet")
c.done()
