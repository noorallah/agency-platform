"""TC-STOCK-009: a stock transfer document: dispatch, in transit, receive, cancel."""
from _inv import *
from _flow import *

c = Check("tc_stock_009")
w = World()
w1, w2 = w.warehouse("A"), w.warehouse("B")
p = w.product()
w.stock_in(w1["id"], p["id"], 50, 60)
ST = f"{INV}/stock-transfers"


def new(qty: str) -> dict:
    """Create a draft transfer of qty from A to B."""
    return must(w.admin.post(ST, {"transfer_date": w.today, "from_warehouse_id": w1["id"],
                                  "to_warehouse_id": w2["id"],
                                  "lines": [{"product_id": p["id"], "quantity": qty}]}), "transfer")


def row(wid: str) -> dict:
    """Inventory row of the product in a warehouse (zeros when none)."""
    for r in w.rows(p["id"]):
        if r["warehouse_id"] == wid:
            return r
    return {k: "0" for k in ("current_quantity", "in_transit_quantity", "available_quantity",
                             "blocked_quantity", "damaged_quantity")}


t = new("20")
c.ok(t["transfer_number"].startswith("TO-"), "numbered TO-", t["transfer_number"])
c.eq(t["status"], "DRAFT", "draft")
c.eq(D(row(w1["id"])["current_quantity"]), D(50), "a draft moves nothing")
books_before = w.inventory_account()
st, b = w.admin.post(f"{ST}/{t['id']}/dispatch", {})
c.eq(st, 200, "dispatched")
c.eq((D(row(w1["id"])["current_quantity"]), D(row(w2["id"])["in_transit_quantity"]),
      D(row(w2["id"])["available_quantity"])), (D(30), D(20), D(0)), "30 at source, 20 in transit, none available at destination")
c.eq(len(entries(w, t["transfer_number"])), 0, "no journal at dispatch")
c.eq(w.inventory_account(), books_before, "books do not move at dispatch")
st, b = w.admin.get(f"{ST}/{t['id']}/challan")
c.ok(st == 200 and isinstance(b, bytes) and b[:4] == b"%PDF", "challan is a PDF", (st, str(b)[:60]))
st, b = w.admin.put(f"{ST}/{t['id']}", {"transfer_date": w.today, "from_warehouse_id": w1["id"],
                                         "to_warehouse_id": w2["id"],
                                         "lines": [{"product_id": p["id"], "quantity": "5"}]})
c.ok(st in (409, 422), "a dispatched transfer cannot be edited", (st, message(b)))
st, b = w.admin.post(f"{ST}/{t['id']}/receive", {"lines": [{"line_number": 1, "received_quantity": "18", "damaged_quantity": "3"}]})
c.eq(st, 200, "received 18 of which 3 damaged")
got = data(b)
c.eq(got["status"], "RECEIVED", "RECEIVED")
c.eq((D(got["dispatched_value"]), D(got["shortage_value"])), (D(1200), D(120)), "dispatched 1200, shortage 120")
r2 = row(w2["id"])
c.eq((D(r2["current_quantity"]), D(r2["in_transit_quantity"]), D(r2["available_quantity"]),
      D(r2["blocked_quantity"])), (D(18), D(0), D(15), D(3)), "18 held: 15 sellable, 3 blocked, nothing in transit")
js = entries(w, t["transfer_number"])
c.eq(len(js), 1, "one journal for the 2 that never arrived")
if js:
    net = by_purpose(w, js[0])
    c.eq((net.get("INVENTORY_ADJUSTMENT"), net.get("INVENTORY")), (D(120), D(-120)), "Dr adjustment 120 / Cr inventory 120")
c.eq(w.inventory_account(), books_before - D(120), "the books fall by the shortage only")
c.refused(w.admin.post(f"{ST}/{t['id']}/cancel", {"reason": "late"}), 422, "final", "a received transfer cannot be cancelled")
# a second transfer, cancelled after dispatch
t2 = new("5")
c.eq(w.admin.post(f"{ST}/{t2['id']}/dispatch", {})[0], 200, "second dispatched")
c.eq(D(row(w1["id"])["current_quantity"]), D(25), "25 left at source")
st, b = w.admin.post(f"{ST}/{t2['id']}/cancel", {"reason": "changed mind"})
c.eq(st, 200, "cancel after dispatch accepted")
c.eq((D(row(w1["id"])["current_quantity"]), D(row(w2["id"])["in_transit_quantity"])), (D(30), D(0)), "stock returned to source, nothing in transit")
# a third, cancelled as a draft
t3 = new("4")
st, b = w.admin.post(f"{ST}/{t3['id']}/cancel", {"reason": "typo"})
c.eq(st, 200, "draft cancelled")
c.eq(D(row(w1["id"])["current_quantity"]), D(30), "a cancelled draft moved nothing")
# more than free
t4 = new("500")
st, b = w.admin.post(f"{ST}/{t4['id']}/dispatch", {})
c.ok(st in (409, 422), "dispatching more than is free is refused", (st, message(b)))
c.eq(D(row(w1["id"])["current_quantity"]), D(30), "nothing left the source")
c.done()
