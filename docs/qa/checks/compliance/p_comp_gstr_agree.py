"""Probe: GSTR-1 and GSTR-3B agree on mixed B2B local, B2B interstate and B2CS bills (firm two, deltas)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _comp import *

c = Check("p_comp_gstr_agree")
o = Own("two")
a = o.api
b1 = gstr1(a)
t1, t3 = gstr1_totals(b1), gstr3b(a)["outward_taxable_supplies"]
c.eq((D(t3["taxable_value"]), D(t3["central_tax"]), D(t3["state_tax"]), D(t3["integrated_tax"])), (t1["taxable"], t1["cgst"], t1["sgst"], t1["igst"]), "before: 3B equals GSTR-1")
local = o.bill(o.customer(o.gstin("33")), "3")
inter = o.bill(o.customer(o.gstin("29")), "2")
walk = o.bill(o.customer(), "4")
r1 = gstr1(a)
n1 = gstr1_totals(r1)
d = {k: n1[k] - t1[k] for k in n1}
c.eq(d, {"taxable": D(900), "cgst": D(27 + 36), "sgst": D(27 + 36), "igst": D(36)}, "GSTR-1 moved by 900.00 taxable, CGST/SGST 63.00 each, IGST 36.00")
r3 = gstr3b(a)["outward_taxable_supplies"]
c.eq((D(r3["taxable_value"]), D(r3["central_tax"]), D(r3["state_tax"]), D(r3["integrated_tax"])), (n1["taxable"], n1["cgst"], n1["sgst"], n1["igst"]), "after: 3B 3.1(a) still equals GSTR-1")
pos = {inv["invoice_number"]: (inv["place_of_supply"], D(inv["integrated_tax"]), D(inv["central_tax"])) for p in r1["b2b"] for inv in p["invoices"]}
c.eq(pos[local["invoice_number"]], ("33", D(0), D(27)), "the local bill is CGST+SGST in place 33")
c.eq(pos[inter["invoice_number"]], ("29", D(36), D(0)), "the interstate bill is IGST in place 29")
c.ok(not r1["unplaced_invoices"], "no bill without a place of supply")
hsn_t = sum(D(x["taxable_value"]) for x in r1["hsn"])
c.eq(hsn_t, n1["taxable"], "the HSN summary taxable equals the sections' taxable")
docs = r1["docs"]
c.eq(sum(x["net_issued"] for x in docs), sum(x["count"] for x in docs), "document series: issued less cancelled equals count")
c.done()
