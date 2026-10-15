"""Probe: another firm's bill cannot be printed, sized up, or put in a run."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _prt import *

c = Check("p_prt_other_firm")
a = admin()
b = admin("admin2")
sc = Scene(a, stock="50")
with counter(a):
    mine = sc.bill()
bid = mine["id"]
c.eq(a.raw(f"{SI}/{bid}/print")[0], 200, "the owner prints it")
c.eq(b.raw(f"{SI}/{bid}/print")[0], 404, "firm two cannot print firm one's bill")
c.eq(b.raw(f"{SI}/{bid}/print?paper=A4")[0], 404, "nor with a paper choice")
c.eq(b.get(f"{SI}/{bid}/print/paper")[0], 404, "nor ask which paper it needs")
status, raw = post_raw(b, f"{SI}/bulk-print", {"invoice_ids": [bid]})
c.eq(status, 404, "nor put it in a run")
status, raw = post_raw(a, f"{SI}/bulk-print", {"invoice_ids": [bid, mine["id"]]})
c.eq(status, 200, "a run naming the bill twice still prints for its owner")
# a member of firm one naming firm two in the header
c.eq(a.inside(b.firm_id).raw(f"{SI}/{bid}/print")[0], 403, "firm one's admin naming firm two's id is refused")
c.eq(Api(a.token, None).raw(f"{SI}/{bid}/print")[0] in (400, 403, 422), True, "no firm header is refused")
c.done()
