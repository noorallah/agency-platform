"""Probe: write off from a named lot beyond what it holds; the confirm flag does not override an off switch."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _lot import *  # noqa: F401,F403

c0 = Check("p_write_off_named_lot")
api = lot_admin(); c = Ctx(api)
lot_settings(api, False)
p = c.product("B")
lots = two_lots(c, p, 10, 10)
s, body = c.write_off(p, "11", batch_id=lots["a"]["id"])
c0.ok(s == 422, "writing 11 off a lot that holds 10 is refused", (s, message(body)[:200]))
s, body = c.write_off(p, "4", batch_id=lots["b"]["id"])
c0.eq(s, 201, f"4 off LOTB accepted ({message(body)[:100]})")
rows = lotmap(c, p)
c0.eq((D(rows["LOTA"]["quantity"]), D(rows["LOTB"]["quantity"]), D(rows["LOTB"]["value"])), (D(10), D(6), D(252)), "LOTB 6 left at 42")
q = c.product("P", batch=False, allow_negative_stock=True)
c.receive([{"product": q, "qty": 1, "rate": 30}])
nid = c.note([{"product": q, "qty": 3}])["note"]["id"]
s, body = c.dispatch(nid, confirm=True)
c0.ok(s == 422, "confirming does not allow billing without stock when the firm has not switched it on", (s, message(body)[:200]))
c0.done()
