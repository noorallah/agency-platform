"""Probe (round 5): units a customer sends back as scrap stand in the damaged bucket, and a write-off takes them first (D-STK-46).

Twenty in at 60, ten sold. Two come back as scrap: the shelf still holds ten, the damaged bucket two, and the books
carry them. A write-off of two empties the damaged bucket and leaves the shelf alone; the books fall by their cost and
the trial balance agrees with the valuation. A second scrap return, cancelled, takes its unit out of the bucket again."""
from _inv import *
from _flow import *

c = Check("p_scrap_return")
w = World()
wh = w.warehouse()
p = w.product()
w.stock_in(wh["id"], p["id"], 20, 60)
s = sell_and_dispatch(w, wh["id"], p["id"], 10)
c.eq(s["dispatch"][0], 200, "10 dispatched")
note = must(w.admin.get(f"/api/v1/delivery-notes/{s['note']['id']}"), "note")


def row() -> tuple[Decimal, Decimal, Decimal]:
    """(shelf, damaged, quarantine) of the product's one row."""
    x = w.rows(p["id"])[0]
    return D(x["current_quantity"]), D(x["damaged_quantity"]), D(x["quarantine_quantity"])


def scrap_return(quantity: int) -> dict:
    """Raise, approve and complete a return whose units are all scrap."""
    r = must(w.admin.post("/api/v1/sales-returns", {
        "customer_id": w.customer_id, "warehouse_id": wh["id"], "return_date": w.today,
        "lines": [{"source_document_type": "DELIVERY_NOTE", "source_document_id": note["id"],
                   "source_document_line_id": note["lines"][0]["id"], "line_number": 1,
                   "current_return_quantity": str(quantity), "restock_quantity": "0", "damaged_quantity": "0",
                   "scrap_quantity": str(quantity), "warehouse_id": wh["id"]}]}), "return")
    must(w.admin.post(f"/api/v1/sales-returns/{r['id']}/approve", {}), "approve return")
    st, b = w.admin.post(f"/api/v1/sales-returns/{r['id']}/complete", {})
    c.eq(st, 200, f"a return of {quantity} as scrap is completed: " + message(b)[:120])
    return r


c.eq(row(), (D(10), D(0), D(0)), "before: ten on the shelf, nothing damaged")
books_sold = w.inventory_account()
scrap_return(2)
c.eq(row(), (D(10), D(2), D(0)), "two back as scrap: the shelf is as it was and the damaged bucket holds two")
books_back = w.inventory_account()
c.eq(books_back - books_sold, D(120), "the books carry the two at their cost (120)")
st, b = w.admin.post(f"{INV}/write-offs", {"branch_id": w.branch_id, "warehouse_id": wh["id"], "product_id": p["id"],
                                            "quantity": "2", "reason": "DAMAGE", "transaction_date": w.today,
                                            "reference_number": f"SCR{w.tag}"})
c.ok(st in (200, 201), "the two are written off", (st, message(b)[:200]))
c.eq(row(), (D(10), D(0), D(0)), "the write-off took the damaged units first: bucket empty, shelf untouched")
c.eq(w.inventory_account() - books_back, D(-120), "the books fall by their cost (120)")
value = next((D(v["value"]) for v in w.valuation() if v.get("product_code") == p["code"]), None)
c.eq(value, D(600), "the valuation holds ten at 60")
periods = data(w.admin.get("/api/v1/finance/accounting-periods?page_size=50")[1])
cur = next(x for x in periods if x["starts_on"] <= w.today <= x["ends_on"])
tb = data(w.admin.get(f"/api/v1/finance/trial-balance?accounting_period_id={cur['id']}")[1])
line = next((l for l in tb["lines"] if l["account_code"] == "1200"), None)
c.ok(line is not None and D(line["closing_balance"]) == w.inventory_account(), "the trial balance's Inventory is the books figure",
     line and line["closing_balance"])
# a write-off of more than the firm holds anywhere is still refused
st, b = w.admin.post(f"{INV}/write-offs", {"branch_id": w.branch_id, "warehouse_id": wh["id"], "product_id": p["id"],
                                            "quantity": "11", "reason": "DAMAGE", "transaction_date": w.today,
                                            "reference_number": f"SCX{w.tag}"})
c.ok(st in (409, 422), "a write-off past shelf and damaged together is refused", (st, message(b)[:160]))
c.eq(row(), (D(10), D(0), D(0)), "and moved nothing")
# a cancelled scrap return takes its unit out of the bucket again
r2 = scrap_return(1)
c.eq(row(), (D(10), D(1), D(0)), "a second scrap return: one in the damaged bucket")
st, b = w.admin.post(f"/api/v1/sales-returns/{r2['id']}/cancel", {"reason": "booked by mistake"})
c.eq(st, 200, "the completed return is cancelled: " + message(b)[:120])
c.eq(row(), (D(10), D(0), D(0)), "cancelling takes the scrap unit out of the bucket again")
c.eq(w.inventory_account() - books_back, D(-120), "and the books are where the write-off left them")
c.done()
