"""TC-LOT-009: a firm by lot never runs below zero (billing without stock off)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _lot import *  # noqa: F401,F403

c0 = Check("tc_lot_009")
api = lot_admin(); c = Ctx(api)
lot_settings(api, False)
for label, allow in (("a product that forbids negative stock", False), ("a product that allows negative stock", True)):
    q = c.product("P" + ("Y" if allow else "N"), batch=False, allow_negative_stock=allow)
    receipt = c.receive([{"product": q, "qty": 8, "rate": 30}])
    s, body = c.adjust(q, "-9")
    c0.ok(s == 422 and ("9" in message(body) or "short" in message(body).lower() or "enough" in message(body).lower()),
          f"{label}: adjusting down by 9 is refused naming the shortage", (s, message(body)[:200]))
    s, body = purchase_return(c, receipt, "9")
    c0.ok(s in (400, 409, 422), f"{label}: a purchase return of 9 is refused", (s, message(body)[:200]))
    made = c.note([{"product": q, "qty": 9}])
    s, body = c.dispatch(made["note"]["id"])
    c0.ok(s == 422 and "stock" in message(body).lower(), f"{label}: dispatching 9 is refused naming the shortage", (s, message(body)[:200]))
    c0.eq(c.stock(q), D(8), f"{label}: the stock still reads 8")
c0.done()
