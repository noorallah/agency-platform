"""TC-COMP-022: a filed return is kept, a change becomes an amendment (firm two, last month; filing withdrawn at the end)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _comp import *

c = Check("tc_comp_022")
o = Own("two")
a = o.api
first, last, period = last_month()
cust = o.customer(o.gstin())
b1 = o.bill(cust, "2", on=last)
c.ok(b1["invoice_number"] in invoice_numbers(gstr1(a, first, last)), "the bill is in last month's GSTR-1")
st, body = a.post(f"{GST}/filings", {"return_type": "GSTR1", "return_period": period, "filed_on": today().isoformat(), "arn": "AA0000000022"})
c.eq(st, 200, "last month's GSTR-1 marked filed")
fid = data(body)["id"]
b2 = None
try:
    c.eq(gstr1(a, first, last)["filed"], True, "the period reads as filed")
    b2 = o.bill(cust, "1", on=last)
    c.ok(b2["invoice_number"] not in invoice_numbers(gstr1(a, first, last)), "a bill added afterwards is not in the filed figures")
    added = [x["key"][1] for x in gstr1(a)["amendments"]["added"]]
    c.ok(b2["invoice_number"] in added, "it shows as an amendment on this month's GSTR-1", added)
    n = gstr3b(a)["amendments_to_earlier_returns"]
    c.ok(D(n["taxable_value"]) >= D(100), "and in GSTR-3B's amendments to earlier returns", n)
finally:
    c.eq(a.delete(f"{GST}/filings/{fid}")[0], 200, "filing withdrawn")
r = gstr1(a, first, last)
c.eq(r["filed"], False, "the period is live again")
if b2:
    c.ok(b2["invoice_number"] in invoice_numbers(r), "and the late bill is in it")
c.done()
