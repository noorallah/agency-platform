"""TC-COMP-002: what rests on a bill stops it being cancelled; a return follows what is left (firm two)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _comp import *

c = Check("tc_comp_002")
o = Own("two")
a = o.api
A = o.f["invoices"]["A"]
c.refused(a.post(f"{SI}/{A}/cancel", {"reason": "check"}), 422, "cannot be cancelled while it has", "collected + registered invoice A cannot be cancelled")
c.ok("registration" in message(a.post(f"{SI}/{A}/cancel", {"reason": "check"})[1]), "and the refusal names its registration")
before = gstr1(a)
walk = o.customer()
bill = o.bill(walk, "3")
mid = gstr1(a)
d1 = gstr1_totals(mid)["taxable"] - gstr1_totals(before)["taxable"]
c.eq(d1, D(300), "an approved B2C bill of 3 adds 300.00 to GSTR-1")
hq = lambda r: sum(D(x["quantity"]) for x in r["hsn"])  # noqa: E731
ht = lambda r: sum(D(x["taxable_value"]) for x in r["hsn"])  # noqa: E731
c.eq(ht(mid) - ht(before), D(300), "and 300.00 to the HSN taxable")
done = a.post(f"{SI}/{bill['id']}/cancel", {"reason": "check cancel"})
c.eq(done[0], 200, "the unregistered B2C bill cancels")
after = gstr1(a)
c.eq(gstr1_totals(after), gstr1_totals(before), "the B2CS contribution is gone again")
c.eq((hq(after), ht(after)), (hq(before), ht(before)), "HSN quantity and taxable fall back")
c.done()
