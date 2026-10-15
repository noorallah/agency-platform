"""Probe: a sandbox registration is never mistaken for a filing (both firms, read only except one refused write)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _comp import *

c = Check("p_comp_sandbox_marks")
for who in ("admin", "admin2"):
    a = api(who)
    rows = all_rows(a, f"{EINV}/registrations", 25)
    c.ok(rows, f"{who}: has registrations")
    for x in rows:
        if x["mode"] == "SANDBOX":
            c.ok(x["status"] != "REGISTERED" or (str(x["irn"]).startswith("SBX") and str(x["acknowledgement_number"]).startswith("SBX")), f"{who}: a sandbox row's IRN and Ack are SBX-marked", x["invoice_number"])
            c.ok(not x["signed_qr_code"] or str(x["signed_qr_code"]).startswith("SANDBOX"), f"{who}: its QR text is marked SANDBOX", x["invoice_number"])
        else:
            c.eq(x["provider"], "OFFLINE", f"{who}: a LIVE row can only come from the Offline route ({x['invoice_number']})")
            c.ok(not str(x["irn"] or "").startswith("SBX"), f"{who}: an SBX reference is never on a LIVE row")
    c.eq(sum(1 for x in rows if x["mode"] not in ("SANDBOX", "LIVE")), 0, f"{who}: only SANDBOX or LIVE appear")
a = api("admin2")
c.refused(a.put(f"{EINV}/settings", {"provider": "LIVE"}), 422, "not available", "the LIVE route cannot be chosen")
c.ok("LIVE" not in data(a.get(f"{EINV}/settings")[1])["available"], "and is not on offer")
a1 = api("admin")
for key in ("A", "B"):
    e = data(a1.get(f"{EINV}/invoices/{firm('one')['invoices'][key]}/eway-bill")[1])
    c.ok(e is None or str(e["eway_bill_number"]).startswith("SBX"), "an e-way bill number from the sandbox is SBX-marked")
c.done()
