"""TC-LOT-021: cost and margin on the line, only with the cost permission (HTTP steps 1 and 3).

Not driven: step 2 (screen figures dropping as the quantity is edited) and step 4 (print and
PDF carry no cost or margin; screen/print only). The user without PRODUCT_VIEW_COST_PRICE is
the fixture's Viewer; the one with it is the Firm admin.
"""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _lot import *  # noqa: F401,F403

c0 = Check("tc_lot_021")
api = lot_admin(); c = Ctx(api); p = margin_product(api)
g = c.receive([{"product": p, "qty": 10, "rate": 80}])
lot = lot_of_receipt(api, p, receipt_line(api, g))
made = c.note([{"product": p, "qty": 2, "picks": [(lot["id"], 2)]}], price="100")
order_id = made["order"]["id"]
o = must(api.get(f"/api/v1/sales-orders/{order_id}"), "order read")
ol = o["lines"][0]
c0.eq((D(ol.get("cost_amount")), D(ol.get("margin_amount")), D(ol.get("margin_percent"))),
      (D(160), D(40), D(25)), "(1) the order line: cost 160, margin 40, 25 % of cost")
c0.eq(ol.get("cost_is_estimate"), True, "(1) the order's cost is marked an estimate")
must(c.dispatch(made["note"]["id"]), "dispatch")
inv = c.bill(made["note"])
il = inv["lines"][0]
c0.eq((D(il.get("gross_amount")), D(il.get("cost_amount")),
       D(il.get("margin_amount")), D(il.get("margin_percent"))),
      (D(200), D(160), D(40), D(25)), "(1) the bill line: gross (taxable) 200, cost 160, margin 40, 25 %")
c0.eq((D(inv.get("cost_total")), D(inv.get("margin_total"))), (D(160), D(40)), "(1) the bill totals")
c0.eq(il.get("cost_is_estimate"), False, "(1) a dispatched bill's cost is not an estimate")
v = client("viewer", "lots")
s, b = v.get(f"/api/v1/sales-invoices/{inv['id']}")
c0.eq(s, 200, f"(3) the Viewer can read the bill ({message(b)})")
if s == 200:
    row = data(b); vl = row["lines"][0]
    for name in ("cost_amount", "margin_amount", "margin_percent", "cost_is_estimate"):
        c0.ok(vl.get(name) in (None, False), f"(3) the line holds no {name} for the Viewer", vl.get(name))
    for name in ("cost_total", "margin_total"):
        c0.ok(row.get(name) is None, f"(3) the bill holds no {name} for the Viewer", row.get(name))
s, b = v.get(f"/api/v1/sales-orders/{order_id}")
if s == 200:
    vl = data(b)["lines"][0]
    c0.ok(vl.get("cost_amount") is None and vl.get("margin_amount") is None,
          "(3) the order line holds no cost or margin for the Viewer", vl.get("cost_amount"))
c0.done()
