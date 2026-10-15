"""Probe: a product sold and bought in BOX with 1 BOX = 12 PIECE answers a pack of 12 BOX."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _bp import *  # noqa: F401,F403

c0 = Check("p_bp_01"); api = bp_admin(); c = Ctx(api); p = pack_product(api, c)
row = must(api.get(f"/api/v1/products/{p['id']}"), "product")
c0.eq((D(row.get("pack_size")), row.get("pack_unit_code")), (D(12), "BOX"), "the selling pack is 12 BOX")
c0.eq((D(row.get("buying_pack_size")), row.get("buying_pack_unit_code")), (D(12), "BOX"), "the buying pack is 12 BOX")
c0.done()
