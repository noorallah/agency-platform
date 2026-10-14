"""TC-LOT-006: two lines of one item from two lots, each at its own lot's cost."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _lot import *  # noqa: F401,F403

c0 = Check("tc_lot_006")
api = lot_admin(); c = Ctx(api)
p = c.product("B")
lots = two_lots(c, p, 10, 10)
made = c.sell([{"product": p, "qty": 2, "picks": [(lots["a"]["id"], 2)]},
               {"product": p, "qty": 2, "picks": [(lots["b"]["id"], 2)]}])
rows = lotmap(c, p)
c0.eq((D(rows["LOTA"]["quantity"]), D(rows["LOTB"]["quantity"])), (D(8), D(8)), "2 left each lot")
inv = c.bill(made["note"])
costs = [x.get("cost_amount") for x in inv["lines"]]
c0.eq([D(x) if x is not None else None for x in costs], [D(80), D(84)],
      "each bill line carries its own lot's cost: 2 x 40.00 and 2 x 42.00 (published on the lines)")
s, body = api.get("/api/v1/sales-invoices/reports/margin-by-lot")
mine = sorted(((r["batch_number"], D(r["quantity"]), D(r["sales_value"]), D(r["cost"]), D(r["margin"]))
               for r in data(body) if r["product_id"] == p["id"]), key=lambda r: r[0]) if s == 200 else []
c0.eq(mine, [("LOTA", D(2), D(200), D(80), D(120)), ("LOTB", D(2), D(200), D(84), D(116))],
      "margin by lot: one row per lot with quantity, sales value, cost and margin")
c0.done()
