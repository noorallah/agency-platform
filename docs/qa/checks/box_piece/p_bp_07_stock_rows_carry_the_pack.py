"""Probe: stock list rows carry pack_size/pack_unit_code when a switch is on, and none with both off.

Turns both switches off for the second half and back on in a finally, as setup left them.
"""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _bp import *  # noqa: F401,F403
c0 = Check("p_bp_07"); api = bp_admin(); c = Ctx(api); p = pack_product(api, c)
c.receive([{"product": p, "qty": 30, "rate": 5}])


def rows() -> list[dict]:
    """Return the stock rows of the pack product."""
    got = rows_of(api.get(f"/api/v1/inventory?search={p['code']}&page_size=20"))
    return [r for r in got if r.get("product_id") == p["id"]]


mine = rows()
c0.ok(mine, "the product has a stock row")
c0.ok(all((D(r.get("pack_size")), r.get("pack_unit_code")) == (D(12), "BOX") for r in mine),
      "with a switch on every row carries pack 12 BOX", [(r.get("pack_size"), r.get("pack_unit_code")) for r in mine])
switches(api, False, False)
try:
    c0.ok(all(r.get("pack_size") is None and r.get("pack_unit_code") is None for r in rows()),
          "with both switches off the rows carry no pack")
finally:
    switches(api, True, True)
c0.done()
