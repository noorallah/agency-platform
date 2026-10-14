"""TC-LOT-012: Stock valuation by lot, Margin by lot and Stock ageing."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _lot import *  # noqa: F401,F403

c0 = Check("tc_lot_012")
api = lot_admin(); c = Ctx(api)
p = c.product("B")
# LOTA received 100 days ago (@40), LOTB today (@42); sell 3 of LOTA, return 1.
c.receive([{"product": p, "qty": 10, "rate": 40, "batch": "LOTA", "expiry": today() + timedelta(days=200), "mrp": 150}], days_ago=100)
c.receive([{"product": p, "qty": 10, "rate": 42, "batch": "LOTB", "expiry": today() + timedelta(days=365), "mrp": 150}])
a = batch_of(c, p, "LOTA")
made = c.sell([{"product": p, "qty": 3, "picks": [(a["id"], 3)]}])
inv = c.bill(made["note"])
s, rb = sales_return(c, inv, "1"); ret = data(rb)
complete_return(c, ret)
# (1) valuation = sum of lots; the lot rows add up; books agree.
rows = c.lots(p)
c0.eq(sorted((r["batch_number"], r["quantity"], r["rate"], r["value"]) for r in rows),
      [("LOTA", "8.0000", "40.000000", "320.00"), ("LOTB", "10.0000", "42.000000", "420.00")],
      "lot report: a row per lot with quantity, cost and value")
c0.ok(all(r[k] for r in rows for k in ("lot_reference", "received_on", "expiry_date", "mrp")),
      "each row carries reference, received date, expiry and MRP", rows[:1])
val = all_rows(api, f"{INV}/reports/stock-valuation?include_zero=true")
mine = [r for r in val if r["row_type"] == "ITEM" and r["product_code"] == p["code"]]
c0.eq((len(mine), D(mine[0]["quantity"]) if mine else None, D(mine[0]["value"]) if mine else None), (1, D(18), D(740)),
      "Stock valuation of the item is the sum of its lots (18 units, 740.00)")
diff = [r for r in val if r["row_type"] == "DIFFERENCE"]
c0.eq(D(diff[0]["value"]) if diff else None, D(0), "the Inventory account and the valuation agree (difference 0)")
# (2) a day before the switch: empty lot report, the valuation reads on Average.
before = rows_of(api.get(f"{INV}/reports/stock-valuation/lots?product_id={p['id']}&to_date=2026-03-31"))
c0.eq(before, [], "a day before the switch the lot report is empty")
# (3) ageing: LOTA is 100 days old at its cost, LOTB new.
age = [r for r in rows_of(api.get(f"{INV}/reports/stock-ageing?page_size=100")) if r["product_code"] == p["code"]]
if age:
    r = age[0]
    c0.eq((D(r["days_91_180"]), D(r["days_0_30"])), (D(8), D(10)), "ageing: 8 units aged 91-180 days (LOTA), 10 under 30 (LOTB)")
else:
    c0.ok(False, "the item is in the ageing report")
# (4) margin by lot: sold 3, returned 1 -> 2 units.
def margin():
    """Return this product's margin rows by batch."""
    s, body = api.get("/api/v1/sales-invoices/reports/margin-by-lot")
    return {r["batch_number"]: r for r in data(body) if r["product_id"] == p["id"]} if s == 200 else {}
m = margin()
c0.eq(sorted(m), ["LOTA"], "one margin row: LOTA")
if m:
    r = m["LOTA"]
    c0.eq((D(r["quantity"]), D(r["sales_value"]), D(r["cost"]), D(r["margin"])), (D(2), D(200), D(80), D(120)),
          "returns taken back: 2 units, sales 200, cost 80, margin 120")
# (5) a new bill counts once approved, not as a draft.
made2 = c.sell([{"product": p, "qty": 2, "picks": [(batch_of(c, p, "LOTB")["id"], 2)]}])
draft = c.bill(made2["note"], approve=False)
c0.eq(sorted(margin()), ["LOTA"], "a draft bill is not counted")
must(api.post(f"/api/v1/sales-invoices/{draft['id']}/approve", {}), "approve")
m = margin()
c0.eq((sorted(m), D(m["LOTB"]["quantity"]) if "LOTB" in m else None), (["LOTA", "LOTB"], D(2)), "the approved bill is counted once")
c0.done()
