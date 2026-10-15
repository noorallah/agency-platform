"""Probe: a pack_size that is not the item's pack, or sent on a line in a non-stock unit, is refused."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _bp import *  # noqa: F401,F403

c0 = Check("p_bp_03"); api = bp_admin(); c = Ctx(api); p = pack_product(api, c)
s, b = api.post("/api/v1/sales-orders", so_body(c, p, "41", pack_size="10"))
c0.ok(s == 422 and "holds 12, not 10" in message(b), "pack_size 10 against a pack of 12 is refused saying a box holds 12", (s, message(b)))
box = box_uom(api)
s, b = api.post("/api/v1/sales-orders", so_body(c, p, "4", pack_size="12", sales_uom_id=box["id"]))
c0.ok(s == 422 and "unit" in message(b).lower(), "pack_size on a line in BOX (not the stock unit) is refused", (s, message(b)))
c0.done()
