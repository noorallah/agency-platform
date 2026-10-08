"""TC-STOCK-006: a delivery short of stock saves but will not dispatch."""
from _inv import *
from _flow import *

c = Check("tc_stock_006")
w = World()
wh = w.warehouse()
p = w.product()
w.stock_in(wh["id"], p["id"], 3)
s = sell_and_dispatch(w, wh["id"], p["id"], 10)
c.eq(s["approve"][0], 200, "order for 10 approves with 3 on hand")
c.eq(s.get("note_create", (0,))[0], 201, "the note saves")
c.eq(s.get("note_approve", (0,))[0], 200, "the note approves")
c.refused(s["dispatch"], 422 if s["dispatch"][0] == 422 else 409, "Insufficient available stock", "dispatch refused")
note = w.admin.get(f"/api/v1/delivery-notes/{s['note']['id']}")[1]["data"]
c.eq(note["status"], "APPROVED", "note stays APPROVED")
c.eq([x for x in w.ledger(p["id"]) if x["transaction_type"] == "DISPATCH"], [], "no DISPATCH in the ledger")
c.eq(w.qty(p["id"]), D(3), "stock unchanged")
c.done()
