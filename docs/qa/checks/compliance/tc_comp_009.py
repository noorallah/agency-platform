"""TC-COMP-009: filing e-invoices offline, export then import (firm two, settings put back)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import json

from _comp import *

c = Check("tc_comp_009")
o = Own("two")
a = o.api
cust = o.customer(o.gstin())
b1, b2, b3 = o.bill(cust), o.bill(cust), o.bill(cust)
c.eq(a.put(f"{EINV}/settings", {"provider": "OFFLINE"})[0], 200, "route switched to Offline")
try:
    st, raw = a._send("POST", f"{EINV}/offline/export", json.dumps({"invoice_ids": [b1["id"], b2["id"]]}).encode(), "application/json")
    c.eq(st, 200, "export answers")
    c.eq(len(raw), 2, "one object per invoice")
    for obj in raw:
        c.ok(all(k in obj for k in ("Version", "TranDtls", "DocDtls", "SellerDtls", "BuyerDtls", "ItemList", "ValDtls")), "portal schema keys present", list(obj))
    c.eq(sorted(x["DocDtls"]["No"] for x in raw), sorted([b1["invoice_number"], b2["invoice_number"]]), "the two invoices")
    for b in (b1, b2):
        r = data(a.get(f"{EINV}/invoices/{b['id']}")[1])
        c.eq((r["status"], r["mode"], r["provider"]), ("PENDING", "LIVE", "OFFLINE"), f"{b['invoice_number']} PENDING / LIVE / OFFLINE")
    result = [
        {"DocDtls": {"No": b1["invoice_number"]}, "Irn": "a" * 64, "AckNo": 123456, "AckDt": "2026-10-16 10:00:00", "SignedQRCode": "QR1"},
        {"DocDtls": {"No": b2["invoice_number"]}, "ErrorDetails": "GSTIN not active"},
    ]
    st, body = a.upload(f"{EINV}/offline/import", "result.json", json.dumps(result).encode())
    c.eq(st, 200, "import answers")
    got = data(body)
    c.eq((got["registered"], got["failed"]), ([b1["invoice_number"]], [b2["invoice_number"]]), "one registered, one refused")
    r1, r2 = (data(a.get(f"{EINV}/invoices/{b['id']}")[1]) for b in (b1, b2))
    c.eq((r1["status"], r1["irn"], r1["acknowledgement_number"]), ("REGISTERED", "a" * 64, "123456"), "first REGISTERED with that IRN and Ack")
    c.eq(r2["status"], "FAILED", "second FAILED")
    c.ok("GSTIN not active" in str(r2["error_message"]), "with the error text", r2["error_message"])
    st, body = a.post(f"{EINV}/invoices/{b3['id']}/register", {})
    r3 = data(body) if st == 200 else {}
    c.ok(st == 422 or r3.get("status") == "FAILED", "Register on a third invoice is refused", (st, r3.get("status")))
    c.ok("export" in str(r3.get("error_message", message(body))).lower(), "with directions to export it instead", r3.get("error_message"))
finally:
    c.eq(a.put(f"{EINV}/settings", {"provider": "SANDBOX"})[0], 200, "route put back to Sandbox")
c.done()
