"""Probe: the paper switch is refused on a full-page or roll firm, and honoured only where it may be."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _prt import *

c = Check("p_prt_paper_on_full_firm")
a = admin()
sc = Scene(a, stock="50")
with counter(a):
    bill = sc.bill()
    for size in ("A4", "A5", "THERMAL80"):
        with template(a, page_size=size):
            status, raw = a.raw(f"{SI}/{bill['id']}/print?paper=HALF")
            c.eq(status, 422, f"{size}: paper=HALF is refused")
            c.ok("Print settings" in refusal_of(raw), f"{size}: the refusal points at Print settings", refusal_of(raw))
            got = must(a.get(f"{SI}/{bill['id']}/print/paper"), "paper")
            c.eq((got["may_choose"], got["customer_paper"]), (False, None), f"{size}: nothing to choose, no customer paper offered")
            c.eq(got["paper"], size, f"{size}: the paper says the firm's own")
    with template(a, page_size="A4"):
        c.eq(a.raw(f"{SI}/{bill['id']}/print?paper=A4")[0], 200, "paper=A4 equals the firm's paper")
c.done()
