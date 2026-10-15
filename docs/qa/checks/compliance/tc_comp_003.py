"""TC-COMP-003: GSTR-3B agrees with GSTR-1 (firm one and firm two)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _comp import *

c = Check("tc_comp_003")
for which, who in (("one", "admin"), ("two", "admin2")):
    a = api(who)
    r1, r3 = gstr1(a), gstr3b(a)
    t = gstr1_totals(r1)
    out = r3["outward_taxable_supplies"]
    c.eq((D(out["taxable_value"]), D(out["central_tax"]), D(out["state_tax"]), D(out["integrated_tax"])),
         (t["taxable"], t["cgst"], t["sgst"], t["igst"]), f"firm {which}: 3.1(a) equals GSTR-1's B2B + B2CL + B2CS")
    c.eq((D(r3["credit_notes_deducted"]["taxable_value"]), D(r3["debit_notes_added"]["taxable_value"])), (D(0), D(0)), f"firm {which}: no notes")
    c.eq(D(r3["net_itc"]["central_tax"]), D(0), f"firm {which}: the inward side is not derived (net ITC 0)")
one = gstr3b(api())["outward_taxable_supplies"]
c.eq((D(one["taxable_value"]), D(one["central_tax"]), D(one["state_tax"])), (D(1800), D(162), D(162)), "firm one: 1800.00 / 162.00 / 162.00")
c.done()
