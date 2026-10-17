"""TC-COMP-003: GSTR-3B agrees with GSTR-1 (firm one and firm two).

The firms already trade, so the check compares before with after its own B2C
bill: 3.1(a) equals GSTR-1 each time, the bill moves 3B by exactly its
200.00 / 18.00 / 18.00, and notes and the inward side do not move.
"""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _comp import *


def outward(r3: dict) -> tuple:
    """3.1(a) as a tuple."""
    o = r3["outward_taxable_supplies"]
    return tuple(D(o[k]) for k in ("taxable_value", "central_tax", "state_tax", "integrated_tax"))


c = Check("tc_comp_003")
for which in ("one", "two"):
    o = Own(which)
    a = o.api
    r1, r3 = gstr1(a), gstr3b(a)
    t = gstr1_totals(r1)
    c.eq(outward(r3), (t["taxable"], t["cgst"], t["sgst"], t["igst"]), f"firm {which}: 3.1(a) equals GSTR-1's B2B + B2CL + B2CS")
    o.bill(o.customer(), "2")
    r1b, r3b = gstr1(a), gstr3b(a)
    t2 = gstr1_totals(r1b)
    c.eq(outward(r3b), (t2["taxable"], t2["cgst"], t2["sgst"], t2["igst"]), f"firm {which}: still equal after a bill")
    c.eq(tuple(x - y for x, y in zip(outward(r3b), outward(r3))), (D(200), D(18), D(18), D(0)), f"firm {which}: the bill moved 3.1(a) by 200.00 / 18.00 / 18.00")
    c.eq((D(r3b["credit_notes_deducted"]["taxable_value"]), D(r3b["debit_notes_added"]["taxable_value"])),
         (D(r3["credit_notes_deducted"]["taxable_value"]), D(r3["debit_notes_added"]["taxable_value"])), f"firm {which}: notes did not move")
    c.eq(D(r3b["net_itc"]["central_tax"]), D(r3["net_itc"]["central_tax"]), f"firm {which}: the inward side did not move")
c.done()
