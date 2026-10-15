"""TC-COMP-018: the 30-day limit and the To register list (firm two; GST document settings put back)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from datetime import timedelta

from _comp import *

c = Check("tc_comp_018")
o = Own("two")
a = o.api
cust = o.customer(o.gstin())
t = today()
with gst_settings(a, einvoice_applicable_from="2026-01-01", thirty_day_rule_from="2026-01-01"):
    old = o.bill(cust, on=(t - timedelta(days=35)).isoformat())
    mid = o.bill(cust, on=(t - timedelta(days=27)).isoformat())
    now = o.bill(cust)
    p = data(a.get(f"{EINV}/pending")[1])
    c.eq(p["thirty_day_rule_applies"], True, "the limit applies once its date is set")
    items = {x["number"]: x for x in p["items"]}
    c.eq(items[old["invoice_number"]]["state"], "LATE", "the 35-day-old bill is Late")
    c.eq(items[old["invoice_number"]]["last_day"], (t - timedelta(days=5)).isoformat(), "its last day is its date + 30")
    c.eq((items[mid["invoice_number"]]["state"], items[mid["invoice_number"]]["days_left"]), ("DUE_SOON", 3), "the 27-day-old bill has 3 days left, due soon")
    c.eq(items[now["invoice_number"]]["state"], "OPEN", "today's bill is Open")
    c.refused(a.post(f"{EINV}/invoices/{old['id']}/register", {}), 422, "last day to register it was", "registering the late bill is refused")
    c.refused(a.post(f"{EINV}/invoices/{old['id']}/register", {}), 422, "raise it again under today's date", "naming what to do")
    c.eq(a.post(f"{EINV}/invoices/{mid['id']}/register", {})[0], 200, "the 27-day-old bill registers")
    c.ok(mid["invoice_number"] not in [x["number"] for x in data(a.get(f"{EINV}/pending")[1])["items"]], "and leaves the list")
c.eq(data(a.get("/api/v1/tax-framework/gst-compliance-settings")[1])["thirty_day_rule_from"], None, "settings put back (30-day date clear)")
p = data(a.get(f"{EINV}/pending")[1])
c.eq(p["thirty_day_rule_applies"], False, "with the date clear the limit does not apply")
c.done()
