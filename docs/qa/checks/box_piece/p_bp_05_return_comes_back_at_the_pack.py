"""Probe: a sales return of 5 pieces off a bill raised at pack 12 comes back at pack 12."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _bp import *  # noqa: F401,F403
c0 = Check("p_bp_05"); api = bp_admin(); c = Ctx(api); p = pack_product(api, c)
sale = boxed_sale(api, c, p)
s, b = sales_return(c, sale["invoice"], "5")
c0.eq(s, 201, f"the return is saved ({message(b)})")
if s == 201:
    ret = must(api.get(f"/api/v1/sales-returns/{data(b)['id']}"), "return read")
    c0.eq(D(ret["lines"][0].get("pack_size")), D(12), "the return line holds pack 12")
    c0.eq(ret.get("box_and_piece_entry"), True, "the return carries the header flag")
c0.done()
