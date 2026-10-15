"""Probe: an order line typed as boxes and pieces (41 pieces, pack 12) is stored at pack 12."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _bp import *  # noqa: F401,F403

c0 = Check("p_bp_02"); api = bp_admin(); c = Ctx(api); p = pack_product(api, c)
s, b = api.post("/api/v1/sales-orders", so_body(c, p, "41", pack_size="12") | {"box_and_piece_entry": True})
c0.eq(s, 201, f"the order is saved ({message(b)})")
if s == 201:
    order = must(api.get(f"/api/v1/sales-orders/{data(b)['id']}"), "order read")
    line = order["lines"][0]
    c0.eq((D(line["quantity"]), D(line.get("pack_size")), order.get("box_and_piece_entry")),
          (D(41), D(12), True), "answers 41 pieces at pack 12 and the header flag on")
c0.done()
