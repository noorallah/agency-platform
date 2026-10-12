"""Probe (backlog 109, S4): the stock valuation states the stock at its MRP beside its cost.

A hand count of three items: one priced by its product, one by its batches
(two with their own MRP, one taking the product's), one with no MRP at all.
"""
from _inv import *

BATCHES = "/api/v1/batch-serial/batches"

c = Check("p_value_at_mrp")
w = World()
wh = w.warehouse()["id"]
other = w.warehouse("X")["id"]

plain = w.product("MP", mrp="65", selling_price="55")
kept = w.product("MB", mrp="40", selling_price="30", track_batch=True)
bare = w.product("MN")

# Two batches with a printed price of their own, one with none.
for number, mrp in (("A", "42"), ("B", "45.50"), ("C", None)):
    body = {"product_id": kept["id"], "warehouse_id": wh, "batch_number": f"{number}{w.tag}"}
    if mrp:
        body["mrp"] = mrp
    must(w.admin.post(BATCHES, body), f"batch {number}")

w.opening(
    wh,
    [
        {"product_id": plain["id"], "quantity": "10", "unit_cost": "50"},
        {"product_id": kept["id"], "quantity": "4", "unit_cost": "25.50", "batch_number": f"A{w.tag}"},
        {"product_id": kept["id"], "quantity": "6", "unit_cost": "25.50", "batch_number": f"B{w.tag}"},
        {"product_id": kept["id"], "quantity": "2", "unit_cost": "25.50", "batch_number": f"C{w.tag}"},
        {"product_id": bare["id"], "quantity": "3", "unit_cost": "100"},
    ],
)
w.stock_in(other, plain["id"], 5, "50")


def rows_of(path: str) -> dict[str, dict]:
    """The valuation's rows keyed by product code, closing rows by their type."""
    return {r["product_code"] or r["row_type"]: r for r in all_rows(w.admin, path, size=100)}


def number(value):
    """A decimal, or None where the report states nothing."""
    return None if value is None else D(value)


before = rows_of(f"{INV}/reports/stock-valuation")
p, k, b = before[plain["code"]], before[kept["code"]], before[bare["code"]]

c.eq(D(p["quantity"]), D(15), "15 of the plain item across two warehouses")
c.eq(D(p["value"]), D("750"), "at cost: 15 x 50")
c.eq(number(p["mrp"]), D("65"), "its MRP is the product's")
c.eq(number(p["mrp_value"]), D("975"), "at MRP: 15 x 65")

c.eq(D(k["quantity"]), D(12), "12 of the batch item")
c.eq(D(k["value"]), D("306"), "at cost: 12 x 25.50")
c.eq(k["mrp"], None, "no one MRP is stated where the batches differ")
c.eq(number(k["mrp_value"]), D("521"), "at MRP: 4 x 42 + 6 x 45.50 + 2 x 40 (the product's)")

c.eq(D(b["value"]), D("300"), "the item with no MRP is still valued at cost")
c.eq(b["mrp"], None, "and states no MRP")
c.eq(b["mrp_value"], None, "and no value at MRP, rather than zero")

c.eq(before["BOOKS"]["mrp_value"], None, "the books row states nothing at MRP")
c.eq(before["DIFFERENCE"]["mrp_value"], None, "nor does the difference")

# The grand total moves by exactly these three items: asked again without them.
total = before["TOTAL"]
mine_cost = D(p["value"]) + D(k["value"]) + D(b["value"])
mine_mrp = D("975") + D("521")
others = [r for code, r in before.items() if code not in (plain["code"], kept["code"], bare["code"]) and r["row_type"] == "ITEM"]
c.eq(D(total["value"]), sum((D(r["value"]) for r in others), mine_cost), "the cost total is the sum of the rows")
c.eq(
    number(total["mrp_value"]),
    sum((D(r["mrp_value"]) for r in others if r["mrp_value"] is not None), mine_mrp),
    "the MRP total is the sum of the rows that state one",
)

# One warehouse: only what it holds.
one = rows_of(f"{INV}/reports/stock-valuation?warehouse_id={other}")
c.eq(number(one[plain["code"]]["mrp_value"]), D("325"), "the second warehouse holds 5 x 65")
c.eq(number(one["TOTAL"]["mrp_value"]), D("325"), "and its MRP total is that")
c.eq(D(one["TOTAL"]["value"]), D("250"), "beside 5 x 50 at cost")

# The export carries the same rows (the screen exports what the route answers).
st, _ = w.admin.get(f"{INV}/reports/stock-valuation?to_date={w.today}&page_size=5")
c.eq(st, 200, "the report pages as before")
c.done()
