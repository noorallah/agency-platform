"""TC-SELL-008: a hold stops a delivery; releasing restores the status it had."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sell import *

c = Check("tc_sell_008")
a = admin()
sc = Scene(a, stock="100")
pid = sc.product["id"]
order = new_order(sc, "12", approve=True)
held = a.post(f"{SO}/{order['id']}/hold", {"reason": "awaiting cheque"})
c.eq(held[0], 200, "hold accepted")
c.ok("is on hold" in str(held[1].get("message")), "message says on hold", held[1].get("message"))
now = must(a.get(f"{SO}/{order['id']}"), "order")
c.eq((now["status"], now["is_on_hold"]), ("APPROVED", True), "status APPROVED, on hold")
line = order["lines"][0]
note = a.post(DN, {"sales_order_id": order["id"], "delivery_date": today().isoformat(),
    "lines": [{"sales_order_line_id": line["id"], "line_number": 1, "current_delivery_quantity": "5"}]})
c.refused(note, 422, "on hold and cannot be dispatched", "a note on a held order is refused on save")
c.ok("awaiting cheque" in message(note[1]), "the refusal quotes the reason", message(note[1]))
c.eq(stock(a, pid)[1], D(12), "reserved stays 12 while held")
rel = a.post(f"{SO}/{order['id']}/release", {})
c.eq(rel[0], 200, "release accepted")
c.ok("released" in str(rel[1].get("message")), "message says released", rel[1].get("message"))
now = must(a.get(f"{SO}/{order['id']}"), "order")
c.eq((now["status"], now["is_on_hold"]), ("APPROVED", False), "plain APPROVED again")
c.done()
