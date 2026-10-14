"""Probe: a purchase return within what was received but beyond what the lot still holds."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _lot import *  # noqa: F401,F403

c0 = Check("p_purchase_return_beyond_stock")
api = lot_admin(); c = Ctx(api)
lot_settings(api, False)
p = c.product("B")
g = c.receive([{"product": p, "qty": 8, "rate": 40, "batch": "LOTA", "expiry": today() + timedelta(days=200), "mrp": 150}])
c.sell([{"product": p, "qty": 5}])
s, body = purchase_return(c, g, "8")
c0.ok(s in (400, 409, 422), "returning 8 to the supplier when 5 were sold is refused", (s, message(body)[:200]))
c0.eq(c.stock(p), D(3), "stock still 3")
s, body = purchase_return(c, g, "3")
c0.eq(s, 200, f"returning the 3 that remain is accepted ({message(body)[:150]})")
c0.eq(c.stock(p), D(0), "lot is empty")
c0.done()
