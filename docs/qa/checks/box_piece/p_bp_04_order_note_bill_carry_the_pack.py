"""Probe: order -> delivery note -> bill carries pack 12 and the boxes-and-pieces header flag."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _bp import *  # noqa: F401,F403
c0 = Check("p_bp_04"); api = bp_admin(); c = Ctx(api); p = pack_product(api, c)
sale = boxed_sale(api, c, p)
for what in ("order", "note", "invoice"):
    doc = sale[what]
    c0.eq((D(doc["lines"][0].get("pack_size")), doc.get("box_and_piece_entry")), (D(12), True),
          f"the {what} line holds pack 12 and the header flag is on")
c0.done()
