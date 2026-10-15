"""TC-COMP-010: e-way bills without an IRN and by hand (firm two).

The 1,000 limit and the Job work delivery note are a setting and a screen flow: skipped.
"""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _comp import *

c = Check("tc_comp_010")
o = Own("two")
a = o.api
cust = o.customer(o.gstin())
b1, b2 = o.bill(cust), o.bill(cust)
due = data(a.get(f"{EINV}/eway-bills/due")[1])
c.ok(D(due["limit"]) > 0, "the due list states the limit", due["limit"])
big = o.bill(cust, "450")
ids = lambda: [x["document_id"] for x in data(a.get(f"{EINV}/eway-bills/due")[1])["items"]]  # noqa: E731
c.ok(big["id"] in ids(), "a bill above the limit with no e-way bill is listed")
c.ok(b1["id"] not in ids(), "a bill under the limit is not")
st, body = a.post(f"{EINV}/invoices/{big['id']}/eway-bill", {"distance_km": "120", "transport_mode": "ROAD", "vehicle_number": "KA01AB1234"})
c.eq(st, 200, "raised on an unregistered B2B invoice while the firm has no e-invoicing date (no IRN needed)")
c.ok(big["id"] not in ids(), "and it leaves the due list")
st, body = a.post(f"{EINV}/eway-bills/record", {"sales_invoice_id": b2["id"], "eway_bill_number": "3510 1234 5678"})
c.eq(st, 200, "a number recorded by hand")
rec = data(body)
c.eq((rec["eway_bill_number"], rec["entered_by_hand"], rec["status"]), ("351012345678", True, "GENERATED"), "stored as 351012345678, marked entered by hand")
c.eq(a.post(f"{EINV}/eway-bills/record", {"sales_invoice_id": b1["id"], "eway_bill_number": "abcdefghijklm"})[0], 422, "a number that is not twelve digits is refused")
c.eq(a.post(f"{EINV}/eway-bills/record", {"sales_invoice_id": b2["id"], "eway_bill_number": "351012345679"})[0], 409, "a second bill on the same invoice is refused")
c.refused(a.post(f"{EINV}/eway-bills/record", {"eway_bill_number": "351012345679"}), 422, "invoice or a delivery note", "naming no document is refused")
c.done()
