"""TC-LOT-007: a sales return goes back into the lots it left, last taken first."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _lot import *  # noqa: F401,F403

c0 = Check("tc_lot_007")
api = lot_admin(); c = Ctx(api)
p = c.product("B")
lots = two_lots(c, p, 10, 10)
made = c.sell([{"product": p, "qty": 5, "picks": [(lots["a"]["id"], 3), (lots["b"]["id"], 2)]}])
inv = c.bill(made["note"])
before = lotmap(c, p)
c0.eq((D(before["LOTA"]["quantity"]), D(before["LOTB"]["quantity"])), (D(7), D(8)), "3 from LOTA and 2 from LOTB")
# (1)-(2) return 4: last lot taken (LOTB) refilled first -> 2 into LOTB, 2 into LOTA.
s, body = sales_return(c, inv, "4")
c0.eq(s, 201, f"return raised ({message(body)})")
ret = data(body) if s == 201 else {}
done = complete_return(c, ret) if ret else (0, None)
c0.eq(done[0], 200, f"return completed ({message(done[1])})")
after = lotmap(c, p)
c0.eq((D(after["LOTA"]["quantity"]), D(after["LOTB"]["quantity"])), (D(9), D(10)),
      "2 back into LOTB, then 2 into LOTA")
c0.eq((after["LOTA"]["rate"], after["LOTB"]["rate"]), (before["LOTA"]["rate"], before["LOTB"]["rate"]),
      "each lot's unit cost does not move")
c0.eq((D(after["LOTA"]["value"]), D(after["LOTB"]["value"])), (D(360), D(420)), "values 9x40 and 10x42")
# (3) a batch the line did not ship.
s, body = sales_return(c, inv, "1", batch_number="NOSUCH")
if s == 201:
    r2 = data(body); done2 = complete_return(c, r2)
    c0.ok(done2[0] in (400, 409, 422) and "did not leave" in message(done2[1]), "a return naming a batch the line did not ship is refused", done2)
else:
    c0.ok(s in (400, 409, 422), "a return naming a batch the line did not ship is refused", (s, message(body)))
# (4) cancel the first return: every movement reverses.
if ret:
    cs, cb = api.post(f"/api/v1/sales-returns/{ret['id']}/cancel", {"reason": "check"})
    c0.eq(cs, 200, f"completed return cancelled ({message(cb)})")
    back = lotmap(c, p)
    c0.eq((D(back["LOTA"]["quantity"]), D(back["LOTB"]["quantity"])), (D(7), D(8)), "the lots hold what they held before")
# (5) more than was sold.
s, body = sales_return(c, inv, "100")
if s == 201:
    r3 = data(body); done3 = complete_return(c, r3)
    c0.ok(done3[0] != 200, "a return of 100 against 5 sold is refused", done3)
else:
    c0.ok(s in (400, 409, 422), "a return of 100 against 5 sold is refused", (s, message(body)))
c0.done()
