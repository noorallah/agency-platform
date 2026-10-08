"""Probe: the Inventory account in the trial balance is the books figure of the stock valuation report, after movements of every kind."""
from _inv import *
from _flow import *

c = Check("p_trial_balance")
w = World()
a = w.warehouse()
p = w.product()
receive(w, a["id"], p["id"], 6, "33.33")
sell_and_dispatch(w, a["id"], p["id"], 2)
base = {"branch_id": w.branch_id, "product_id": p["id"], "transaction_date": w.today, "warehouse_id": a["id"]}
w.admin.post(f"{INV}/write-offs", {**base, "quantity": "1", "reason": "STAFF", "reference_number": f"W{w.tag}"})
periods = data(w.admin.get("/api/v1/finance/accounting-periods?page_size=50")[1])
cur = next(x for x in periods if x["starts_on"] <= w.today <= x["ends_on"])
st, b = w.admin.get(f"/api/v1/finance/trial-balance?accounting_period_id={cur['id']}")
c.eq(st, 200, "trial balance reads")
tb = next((l for l in data(b)["lines"] if l["account_code"] == "1200"), None)
books = next(v for v in w.valuation() if v["row_type"] == "BOOKS")
c.ok(tb is not None, "Inventory (1200) is in the trial balance")
if tb:
    c.eq(D(tb["closing_balance"]), D(books["value"]), "trial balance Inventory = the valuation report's books figure")
lines = data(b)["lines"]
c.eq(sum(D(l["closing_debit"]) for l in lines), sum(D(l["closing_credit"]) for l in lines), "the trial balance balances")
c.done()
