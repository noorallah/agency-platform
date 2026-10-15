"""TC-COMP-023: a quarterly (QRMP) filer (firm two; settings put back).

Driven: the filing plan, the IFF for month 1, the quarterly GSTR-1 range, the IFF refused for month 3,
the PMT-06 suggestion. PMT-06 deposits, the calendar rows for IFF and GST payment for a quarter are skipped.
"""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _comp import *

c = Check("tc_comp_023")
o = Own("two")
a = o.api
with gst_settings(a, filing_frequency="QUARTERLY", quarterly_from="2026-07-01", qrmp_payment_method="FIXED_SUM"):
    plan = data(a.get(f"{GST}/filing-plan")[1])
    c.eq((plan["filing_frequency"], plan["quarterly_from"], plan["qrmp_payment_method"]), ("QUARTERLY", "2026-07-01", "FIXED_SUM"), "the plan reads back what was set")
    iff = data(a.get(f"{GST}/iff?return_period=2026-10")[1])
    c.eq((iff["from_date"], iff["to_date"], iff["due_date"]), ("2026-10-01", "2026-10-31", "2026-11-13"), "IFF for month 1 covers the month, due the 13th")
    q = data(a.get(f"{GST}/gstr1-quarterly?return_period=2026-11")[1])
    c.eq((q["from_date"], q["to_date"]), ("2026-10-01", "2026-12-31"), "the quarterly GSTR-1 for November spans October to December")
    st, body = a.get(f"{GST}/iff?return_period=2026-12")
    c.ok(st in (409, 422), "an IFF for month 3 is refused", (st, message(body)))
    sug = data(a.get(f"{GST}/cash-deposits/suggestion?return_period=2026-10")[1])
    c.eq(sug["method"], "FIXED_SUM", "the PMT-06 suggestion uses the chosen method")
    c.eq(sug["due_date"], "2026-11-25", "and is due the 25th")
c.eq(data(a.get(f"{GST}/filing-plan")[1])["filing_frequency"], "MONTHLY", "frequency put back to Monthly")
c.done()
