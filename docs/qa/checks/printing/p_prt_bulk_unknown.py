"""Probe: a bulk print refuses an unknown id, an empty list, too many ids and a bad body."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _prt import *

c = Check("p_prt_bulk_unknown")
a = admin()
sc = Scene(a, stock="50")
with counter(a):
    bill = sc.bill()
ghost = "00000000-0000-4000-8000-000000000000"
status, raw = post_raw(a, f"{SI}/bulk-print", {"invoice_ids": [ghost]})
c.eq(status, 404, "an unknown id is refused")
status, raw = post_raw(a, f"{SI}/bulk-print", {"invoice_ids": [bill["id"], ghost]})
c.eq(status, 404, "a run with one unknown id prints nothing")
c.ok(raw[:4] != b"%PDF", "the refusal is not a PDF")
c.eq(post_raw(a, f"{SI}/bulk-print", {"invoice_ids": []})[0], 422, "an empty list is refused")
c.eq(post_raw(a, f"{SI}/bulk-print", {"invoice_ids": [bill["id"]] * 101})[0], 422, "101 ids are refused")
c.eq(post_raw(a, f"{SI}/bulk-print", {"invoice_ids": ["not-a-uuid"]})[0], 422, "a malformed id is refused")
c.eq(post_raw(a, f"{SI}/bulk-print", {"invoice_ids": [bill["id"]], "extra": 1})[0], 422, "an unknown field is refused")
c.eq(post_raw(a, f"{SI}/bulk-print", {})[0], 422, "a body with no ids is refused")
c.eq(a.raw(f"{SI}/{ghost}/print")[0], 404, "a single unknown bill is 404")
c.eq(a.get(f"{SI}/{ghost}/print/paper")[0], 404, "its paper is 404 too")
c.done()
