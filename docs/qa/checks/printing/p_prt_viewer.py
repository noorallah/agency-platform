"""Probe: a Viewer prints (viewing is the permission) but cannot save print settings."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _prt import *

c = Check("p_prt_viewer")
a = admin()
v = admin("viewer")
sc = Scene(a, stock="50")
with counter(a):
    bill = sc.bill()
bid = bill["id"]
c.eq(v.raw(f"{SI}/{bid}/print")[0], 200, "a Viewer prints one bill")
c.eq(v.get(f"{SI}/{bid}/print/paper")[0], 200, "a Viewer asks which paper")
status, _ = post_raw(v, f"{SI}/bulk-print", {"invoice_ids": [bid]})
c.eq(status, 200, "a Viewer prints a run")
held = must(a.get(PRINT_TEMPLATE), "template")
base = {k: x for k, x in held.items() if k not in ("id", "document_type", "is_customised")}
c.eq(v.get(PRINT_TEMPLATE)[0], 200, "a Viewer reads the print settings")
c.eq(v.put(PRINT_TEMPLATE, {**base, "upi_id": "viewer@upi"})[0], 403, "a Viewer cannot save print settings")
c.eq(data(a.get(PRINT_TEMPLATE)[1])["upi_id"], held["upi_id"], "nothing was saved")
status, raw = post_raw(v, f"{PRINT_TEMPLATE}/preview", {**base, "bill_layout": "TRADE"})
c.eq(status, 200, "a Viewer may draw the sample (membership is enough)")
c.eq(Api(v.token, None).raw(f"{SI}/{bid}/print")[0] in (400, 403, 422), True, "no firm header is refused")
c.done()
