"""TC-STOCK-001: summary and rows agree; the ledger explains the balance."""
from _inv import *
from _flow import *

c = Check("tc_stock_001")
w = World()
wh = w.warehouse()
p = w.product()
r1 = receive(w, wh["id"], p["id"], 4)
r2 = receive(w, wh["id"], p["id"], 6)
c.eq(r1["status"][0], 200, "first receipt completes")
c.eq(r2["status"][0], 200, "second receipt completes")
rows = w.rows(p["id"])
c.eq(len(rows), 1, "one inventory row")
row = rows[0]
c.eq((D(row["current_quantity"]), D(row["available_quantity"]), D(row["reserved_quantity"])),
     (D(10), D(10), D(0)), "current/available/reserved")
st, b = w.admin.get(f"{INV}/summary/by-product")
mine = [x for x in data(b) if x["scope_id"] == p["id"]]
c.eq(len(mine), 1, "product present in the by-product summary")
if mine:
    c.eq(D(mine[0]["current_quantity"]), D(10), "summary by product agrees with the row")
led = w.ledger(p["id"])
c.eq([(x["transaction_type"], D(x["quantity"])) for x in led],
     [("GOODS_RECEIPT", D(4)), ("GOODS_RECEIPT", D(6))], "ledger rows")
c.eq([D(x["new_current_quantity"]) for x in led], [D(4), D(10)], "balance after each")
c.eq(D(led[-1]["new_current_quantity"]), D(row["current_quantity"]), "last balance equals current")
c.eq([x["reference_number"] for x in led],
     [r1["receipt"]["grn_number"], r2["receipt"]["grn_number"]], "each row names its GRN")
st, b = w.admin.get(f"{INV}/ledger?product_id={p['id']}&transaction_type=GOODS_RECEIPT")
c.eq(len(data(b)), 2, "filter by type keeps both")
st, b = w.admin.get(f"{INV}/ledger?product_id={p['id']}&transaction_type=DISPATCH")
c.eq(len(data(b)), 0, "filter by another type leaves none")
# the books follow the stock: 10 x 60
inv_val = [v for v in w.valuation() if v["product_code"] == p["code"]]
c.eq(D(inv_val[0]["value"]) if inv_val else None, D(600), "valuation of the product")
c.done()
