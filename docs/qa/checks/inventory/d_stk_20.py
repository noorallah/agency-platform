"""D-STK-20: the stock account sits a paisa from the valuation after dispatches at an average cost with more than two decimals."""
from _inv import *
from _flow import *

c = Check("d_stk_20")
w = World()
wh = w.warehouse()
p = w.product()


def totals() -> tuple[Decimal, Decimal]:
    """(valuation total, Inventory account) for the firm."""
    v = {r["row_type"]: D(r["value"]) for r in w.valuation() if r["row_type"] != "ITEM"}
    return v["TOTAL"], v["BOOKS"]


t0, b0 = totals()
receive(w, wh["id"], p["id"], 7, "61.37")
receive(w, wh["id"], p["id"], 5, "49.99")
for _ in range(3):
    s = sell_and_dispatch(w, wh["id"], p["id"], 2)
    c.eq(s["dispatch"][0], 200, "2 dispatched")
t1, b1 = totals()
item = next(v for v in w.valuation() if v["product_code"] == p["code"] and v["row_type"] == "ITEM")
c.eq(b1 - b0, t1 - t0, f"the Inventory account moved by what the valuation moved (valuation row: {item['quantity']} x {item['rate']} = {item['value']})")
c.done()
