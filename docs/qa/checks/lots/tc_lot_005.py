"""TC-LOT-005: dispatch takes the nearest-expiry lot and the bill carries its cost."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _lot import *  # noqa: F401,F403

c0 = Check("tc_lot_005")
api = lot_admin(); c = Ctx(api)
p = c.product("B")
lots = two_lots(c, p, 10, 10)                       # LOTA (+180d) @40, LOTB (+365d) @42
made = c.sell([{"product": p, "qty": 4}])           # no batch chosen
rows = lotmap(c, p)
c0.eq((D(rows["LOTA"]["quantity"]), D(rows["LOTB"]["quantity"])), (D(6), D(10)),
      "the lot expiring first gave the goods, the second is untouched")
note = must(api.get(f"/api/v1/delivery-notes/{made['note']['id']}"), "note")
picks = note["lines"][0]["batches"]
c0.eq([(x["batch_id"], D(x["quantity"])) for x in picks], [(lots["a"]["id"], D(4))], "note line records LOTA 4")
inv = c.bill(made["note"])
line = inv["lines"][0]
c0.eq(D(line.get("cost_amount")) if line.get("cost_amount") is not None else None, D(160),
      "the bill line's cost is LOTA's cost, 4 x 40.00 (published on the bill line)")
c0.ok(not str(line.get("batch_number") or "").startswith("LOT-"), "the bill never prints our LOT reference", line.get("batch_number"))
c0.ok(not str(note["lines"][0].get("batch_number") or "").startswith("LOT-"), "the challan never prints our LOT reference",
      note["lines"][0].get("batch_number"))
# the cost really is the lot's: the margin report says so.
s, body = api.get("/api/v1/sales-invoices/reports/margin-by-lot")
mine = [r for r in data(body) if r["product_id"] == p["id"]] if s == 200 else []
c0.eq([(r["batch_number"], D(r["quantity"]), D(r["cost"])) for r in mine], [("LOTA", D(4), D(160))],
      "margin by lot: LOTA 4 units at cost 160, not the 41 average")
# take LOTA to zero.
made2 = c.sell([{"product": p, "qty": 6}])
rows = lotmap(c, p)
c0.ok("LOTA" not in rows or D(rows["LOTA"]["value"]) == 0, "a lot taken to zero reads zero value", rows.get("LOTA"))
c0.eq(D(rows["LOTB"]["quantity"]), D(10), "LOTB still untouched")
c0.done()
