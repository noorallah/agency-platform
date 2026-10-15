"""TC-MAST-009: one company, two customer accounts (API half: identity-check names the holder; the dialog is screen-only). The case text predates backlog 125: the same GSTIN on a second customer is now refused, and only a repeated PAN is a warning."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _mst import *
from _col import receipt, closing, position, journal
import re
from datetime import timedelta

IMP = "/api/v1/imports"

c = Check("tc_mast_009")
a = api()
t = tag()
pan = ("FX" + tag(3) + "9" + str(abs(hash(t)) % 1000).zfill(3) + "Q")[:10]
pan = "AAACP" + str(abs(hash(t)) % 9000 + 1000) + "C"
g_ho, g_tn = gstin_of(pan, "29"), gstin_of(pan, "33")
ho = must(a.post(CU, {"code": f"HO{t}", "name": f"Head office {t}", "customer_type": "BUSINESS", "currency_code": "INR", "gst_number": g_ho}), "HO")
chk = must(a.get(f"{CU}/identity-check?gst_number={g_ho}"), "check")
c.eq([h["code"] for h in chk["holders"]], [f"HO{t}"], "the check names HO for the GSTIN")
c.ok(f"HO{t}" in str(chk["message"]), "and the warning names it", chk["message"])
ka2 = a.post(CU, {"code": f"KA{t}", "name": f"Second {t}", "customer_type": "BUSINESS", "currency_code": "INR", "gst_number": g_ho})
c.ok(ka2[0] in (409, 422) and f"HO{t}" in message(ka2[1]), "the same GSTIN on a second customer is refused naming the holder (backlog 125; the case says Save anyway saves)", f"{ka2[0]} {message(ka2[1])}")
c.eq(rows_of(a.get(f"{CU}?search=KA{t}")), [], "and nothing is saved")
tn = a.post(CU, {"code": f"TN{t}", "name": f"Other state {t}", "customer_type": "BUSINESS", "currency_code": "INR", "gst_number": g_tn})
c.eq(tn[0], 201, f"another state's GSTIN with the same PAN saves ({message(tn[1])})")
tnrow = must(a.get(f"{CU}/{data(tn[1])['id']}"), "tn")
c.eq(tnrow["pan_number"], pan, "its PAN box is filled from the GSTIN")
chk = must(a.get(f"{CU}/identity-check?pan_number={pan}&excluding_id={tnrow['id']}"), "pan check")
c.eq([h["code"] for h in chk["holders"]], [f"HO{t}"], "the PAN is asked about, naming HO")
dup = a.post(CU, {"code": f"HO{t}", "name": "again", "customer_type": "BUSINESS", "currency_code": "INR"})
c.ok(dup[0] in (409, 422) and f"Customer code HO{t} already exists in this firm" in message(dup[1]), "a second HO code is refused", f"{dup[0]} {message(dup[1])}")
c.done()
