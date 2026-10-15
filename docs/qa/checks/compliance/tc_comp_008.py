"""TC-COMP-008: tax calendar and marking a return filed (firm two, last month's own bill)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _comp import *

c = Check("tc_comp_008")
o = Own("two")
a = o.api
first, last, period = last_month()
o.bill(o.customer(o.gstin()), "2", on=last)
cal = {(x["kind"], x["return_period"]): x for x in rows_of(a.get(f"{GST}/calendar"))}
g1 = cal.get(("GSTR1", period))
c.ok(g1 is not None and ("GSTR3B", period) in cal, "last month has a GSTR-1 and a GSTR-3B row", list(cal))
if g1 and g1["status"] != "DONE":
    c.eq(g1["due_date"], f"{today().strftime('%Y-%m')}-11", "GSTR-1 is due the 11th")
    c.eq(cal[("GSTR3B", period)]["due_date"], f"{today().strftime('%Y-%m')}-20", "GSTR-3B the 20th")
    before3b = cal[("GSTR3B", period)]["status"]
    st, body = a.post(f"{GST}/filings", {"return_type": "GSTR1", "return_period": period, "filed_on": today().isoformat(), "arn": "AA0000000001"})
    c.eq(st, 200, "GSTR-1 recorded as filed")
    fid = data(body)["id"]
    try:
        cal = {(x["kind"], x["return_period"]): x for x in rows_of(a.get(f"{GST}/calendar"))}
        c.eq((cal[("GSTR1", period)]["status"], cal[("GSTR1", period)]["reference"]), ("DONE", "AA0000000001"), "its row reads Filed with the ARN")
        c.eq(cal[("GSTR3B", period)]["status"], before3b, "nothing else moves")
        c.eq(a.post(f"{GST}/filings", {"return_type": "GSTR1", "return_period": period, "filed_on": today().isoformat()})[0], 409, "filing it twice is refused")
    finally:
        c.eq(a.delete(f"{GST}/filings/{fid}")[0], 200, "undo")
    cal = {(x["kind"], x["return_period"]): x for x in rows_of(a.get(f"{GST}/calendar"))}
    c.ok(cal[("GSTR1", period)]["status"] != "DONE", "undo puts the row back")
c.refused(a.post(f"{GST}/filings", {"return_type": "GSTR1", "return_period": today().strftime("%Y-%m"), "filed_on": today().isoformat()}), 422, "filed after the month ends", "a return cannot be filed before its month ends")
c.done()
