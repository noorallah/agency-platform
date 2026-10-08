"""TC-STOCK-018: returned goods are held until checked (reservation lapse needs the server timer: not driven)."""
from _inv import *
from _flow import *

c = Check("tc_stock_018")
w = World()
wh = w.warehouse()
p = w.product()
w.stock_in(wh["id"], p["id"], 20, 60)
SET = "/api/v1/batch-serial/sale-settings"
base_settings = data(w.admin.get(SET)[1])


def settings(hold: bool) -> None:
    """Switch 'hold returned goods for checking' on or off, keeping the rest."""
    body = {k: base_settings[k] for k in ("near_expiry_days", "near_expiry_policy", "fefo_skip_policy", "near_expiry_below_floor")}
    body["hold_returns_for_check"] = hold
    must(w.admin.put(SET, body), "settings")


def row() -> dict:
    """The product's single inventory row."""
    return w.rows(p["id"])[0]


def make_return(note: dict, good: int, damaged: int, scrap: int) -> dict:
    """Raise, approve and complete a return of good + damaged + scrap."""
    nl = note["lines"][0]
    r = must(w.admin.post("/api/v1/sales-returns", {
        "customer_id": w.customer_id, "warehouse_id": wh["id"], "return_date": w.today,
        "lines": [{"source_document_type": "DELIVERY_NOTE", "source_document_id": note["id"],
                   "source_document_line_id": nl["id"], "line_number": 1,
                   "current_return_quantity": str(good + damaged + scrap),
                   "damaged_quantity": str(damaged), "scrap_quantity": str(scrap), "warehouse_id": wh["id"]}]}), "return")
    must(w.admin.post(f"/api/v1/sales-returns/{r['id']}/approve", {}), "approve return")
    return r


try:
    s = sell_and_dispatch(w, wh["id"], p["id"], 10)
    c.eq(s["dispatch"][0], 200, "10 dispatched")
    note = must(w.admin.get(f"/api/v1/delivery-notes/{s['note']['id']}"), "note")
    settings(True)
    r = make_return(note, 3, 2, 0)
    st, b = w.admin.post(f"/api/v1/sales-returns/{r['id']}/complete", {})
    c.eq(st, 200, "return completed")
    x = row()
    c.eq((D(x["current_quantity"]), D(x["quarantine_quantity"]), D(x["damaged_quantity"])), (D(10), D(3), D(2)),
         "with the rule on: the sellable part is in quarantine, the damaged part as before, current unchanged")
    # release the checked goods
    st, b = w.admin.post(f"{INV}/quarantine", {"branch_id": w.branch_id, "warehouse_id": wh["id"], "product_id": p["id"],
                                               "action": "RELEASE", "quantity": "3", "transaction_date": w.today,
                                               "reference_number": f"REL{w.tag}"})
    c.ok(st in (200, 201), "release", (st, message(b)))
    x = row()
    c.eq((D(x["current_quantity"]), D(x["quarantine_quantity"]), D(x["available_quantity"])), (D(13), D(0), D(13)),
         "released goods are on the shelf (13 available)")
    # cancel a second return: it takes the goods back out of quarantine
    r2 = make_return(note, 2, 0, 0)
    st, b = w.admin.post(f"/api/v1/sales-returns/{r2['id']}/complete", {})
    c.eq(st, 200, "second return completed")
    x = row()
    c.eq(D(x["quarantine_quantity"]), D(2), "the second return is held (2)")
    st, b = w.admin.post(f"/api/v1/sales-returns/{r2['id']}/cancel", {"reason": "wrong goods"})
    c.eq(st, 200, "cancel the completed return")
    x = row()
    c.eq((D(x["current_quantity"]), D(x["quarantine_quantity"])), (D(13), D(0)), "cancelling takes it back out of quarantine")
    # off: restock goes straight to the shelf
    settings(False)
    r3 = make_return(note, 1, 0, 0)
    must(w.admin.post(f"/api/v1/sales-returns/{r3['id']}/complete", {}), "complete 3")
    x = row()
    c.eq((D(x["current_quantity"]), D(x["quarantine_quantity"])), (D(14), D(0)), "with the rule off the goods go straight on the shelf")
    # reserve-again on an order that never lapsed
    st, b = w.admin.post(f"/api/v1/sales-orders/{s['order']['id']}/reserve-again", {})
    c.ok(st in (409, 422), "reserve-again on an order that did not lapse is refused", (st, message(b)))
finally:
    settings(base_settings.get("hold_returns_for_check", False))
c.done()
