"""Probe: a transfer of a named lot keeps its cost and lands as a lot at the destination."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _lot import *  # noqa: F401,F403

c0 = Check("p_transfer_named_lot")
api = lot_admin(); c = Ctx(api)
p = c.product("B")
lots = two_lots(c, p, 10, 10)
w2 = c.second_warehouse()
s, body = c.transfer(p, "4", w2, batch_id=lots["b"]["id"])
c0.eq(s, 201, f"transfer of 4 of LOTB accepted ({message(body)[:150]})")
dest = rows_of(api.get(f"{INV}/reports/stock-valuation/lots?product_id={p['id']}&warehouse_id={w2['id']}"))
c0.eq([(r["batch_number"], D(r["quantity"]), D(r["rate"])) for r in dest], [("LOTB", D(4), D(42))], "4 of LOTB at 42 in the second warehouse")
src = rows_of(api.get(f"{INV}/reports/stock-valuation/lots?product_id={p['id']}&warehouse_id={c.warehouse['id']}"))
c0.eq(sorted((r["batch_number"], D(r["quantity"])) for r in src), [("LOTA", D(10)), ("LOTB", D(6))], "source left with 10 and 6")
s, body = c.transfer(p, "7", w2, batch_id=lots["b"]["id"])
c0.ok(s == 422, "transferring 7 of a lot that now holds 6 is refused", (s, message(body)[:200]))
c0.done()
