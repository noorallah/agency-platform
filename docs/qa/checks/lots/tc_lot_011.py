"""TC-LOT-011: a supplier's bill at another rate corrects the lot."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _lot import *  # noqa: F401,F403

c0 = Check("tc_lot_011")
api = lot_admin(); c = Ctx(api)
p = c.product("B")
g = c.receive([{"product": p, "qty": 10, "rate": 40, "batch": "LOTA", "expiry": today() + timedelta(days=200), "mrp": 150}])
c.sell([{"product": p, "qty": 3}])
# (1)-(2) bill at 44 for 10: 7 held take 7 x 4 = 28 into the lot, the 3 sold take 12 to variance.
s, body = supplier_bill(c, g, "10", "44")
c0.eq(s, 200, f"bill at 44 approved ({message(body)})")
bill = data(body) if s == 200 else {}
row = lotmap(c, p).get("LOTA", {})
c0.eq((D(row.get("quantity")), D(row.get("rate")), D(row.get("value"))), (D(7), D(44), D(308)),
      "the lot's unit cost rises by the extra for the 7 held (rate 44, value 308)")
debits = sorted(D(l["debit_amount"]) for e in journal_lines(api, bill.get("invoice_number", "NONE")) for l in e["lines"] if D(l["debit_amount"]))
c0.ok(D(28) in debits and D(12) in debits, "the bill's journal puts 28.00 to the lot and 12.00 (the 3 sold) to variance", debits)
# (3) cancel the bill.
cs, cb = api.post(f"/api/v1/purchase-invoices/{bill.get('id')}/cancel", {"reason": "check"})
c0.eq(cs, 200, f"bill cancelled ({message(cb)})")
row = lotmap(c, p).get("LOTA", {})
c0.eq((D(row.get("quantity")), D(row.get("rate")), D(row.get("value"))), (D(7), D(40), D(280)),
      "after the cancel the lot gives back its 28 (rate 40, value 280)")
# (4) a bill at 38.
s, body = supplier_bill(c, g, "10", "38")
c0.eq(s, 200, f"bill at 38 approved ({message(body)})")
row = lotmap(c, p).get("LOTA", {})
c0.eq((D(row.get("quantity")), D(row.get("rate")), D(row.get("value"))), (D(7), D(38), D(266)),
      "the lot takes the cheaper rate for the 7 held (rate 38, value 266)")
c0.done()
