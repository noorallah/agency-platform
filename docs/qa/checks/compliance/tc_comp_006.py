"""TC-COMP-006: raising and withdrawing an e-way bill (firm two, own bills)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _comp import *

c = Check("tc_comp_006")
o = Own("two")
a = o.api
b2b = o.bill(o.customer(o.gstin()))
o.register(b2b)
EW = f"{EINV}/invoices/{b2b['id']}/eway-bill"
c.refused(a.post(EW, {"distance_km": "120", "transport_mode": "ROAD"}), 422, "need a vehicle number", "road with no vehicle is refused")
c.eq(data(a.get(EW)[1]), None, "and nothing was raised")
st, body = a.post(EW, {"distance_km": "120", "transport_mode": "ROAD", "vehicle_number": "TN01AB1234"})
c.eq(st, 200, "with the vehicle the bill is raised")
bill = data(body)
c.eq(bill["status"], "GENERATED", "status GENERATED")
c.ok(str(bill["eway_bill_number"]).startswith("SBX"), "the number is marked SBX", bill["eway_bill_number"])
c.eq(bill["mode"], "SANDBOX", "mode SANDBOX")
c.eq(a.post(EW, {"distance_km": "120", "transport_mode": "ROAD", "vehicle_number": "TN01AB1234"})[0], 409, "a second live bill is refused")
st, body = a.post(f"{EW}/cancel", {"reason": "check withdraw"})
c.eq((st, data(body)["status"]), (200, "CANCELLED"), "withdrawn")
c.eq(a.post(f"{EW}/cancel", {})[0], 422, "a withdrawal needs a reason")
# Step 3: the refusal needs the firm to e-invoice (a dated setting). With it
# set, an unregistered B2B bill is refused; a B2C bill never is (the case text
# says Invoice C is refused, but C is a consumer's bill: correction).
with gst_settings(a, einvoice_applicable_from="2026-01-01"):
    unreg = o.bill(o.customer(o.gstin()))
    c.refused(a.post(f"{EINV}/invoices/{unreg['id']}/eway-bill", {"distance_km": "120", "transport_mode": "ROAD", "vehicle_number": "TN01AB1234"}), 422, "Register the invoice before raising its e-way bill", "an unregistered B2B bill is refused")
    b2c = o.bill(o.customer())
    st, body = a.post(f"{EINV}/invoices/{b2c['id']}/eway-bill", {"distance_km": "120", "transport_mode": "ROAD", "vehicle_number": "TN01AB1234"})
    c.eq(st, 200, "CASE TEXT: a B2C bill (Invoice C) raises its e-way bill from the invoice, not a 422")
c.done()
