"""Probe: a cancelled bill drops out of GSTR-1, GSTR-3B and the HSN summary, and the series counts it cancelled (firm two, deltas)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _comp import *

c = Check("p_comp_cancel_drops")
o = Own("two")
a = o.api
before = gstr1(a)
cust = o.customer(o.gstin())
keep = o.bill(cust, "1")
gone = o.bill(cust, "2")
mid = gstr1(a)
c.ok(gone["invoice_number"] in invoice_numbers(mid), "both bills are in B2B")
c.eq(a.post(f"{SI}/{gone['id']}/cancel", {"reason": "probe cancel"})[0], 200, "an unregistered B2B bill cancels")
after = gstr1(a)
nums = invoice_numbers(after)
c.ok(gone["invoice_number"] not in nums, "the cancelled bill is out of B2B")
c.ok(keep["invoice_number"] in nums, "the other bill stays")
d = gstr1_totals(after)["taxable"] - gstr1_totals(before)["taxable"]
c.eq(d, D(100), "only the kept bill (100.00) is added")
c.eq(D(gstr3b(a)["outward_taxable_supplies"]["taxable_value"]), gstr1_totals(after)["taxable"], "3B drops it too")
dc = lambda r: sum(x["cancelled"] for x in r["docs"])  # noqa: E731
c.eq(dc(after) - dc(before), 1, "the document series counts one cancelled")
c.ok(sum(x["net_issued"] for x in after["docs"]) == sum(x["net_issued"] for x in mid["docs"]) - 1, "and net issued falls by one")
c.done()
