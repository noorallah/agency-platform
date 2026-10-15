"""TC-SELL-005: an accepted quotation converts once."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sell import *

c = Check("tc_sell_005")
a = admin()
sc = Scene(a, stock="50")
quote = must(a.post(QT, {
    "customer_id": sc.customer["id"], "quotation_date": today().isoformat(),
    "valid_until": (today() + timedelta(days=15)).isoformat(),
    "branch_id": sc.branch["id"], "warehouse_id": sc.warehouse["id"],
    "lines": [{"line_number": 1, "product_id": sc.product["id"], "quantity": "12"}],
}), "quotation")
c.eq(quote["status"], "DRAFT", "a new quotation is a draft")
c.eq(must(a.post(f"{QT}/{quote['id']}/send", {}), "send")["status"], "SENT", "marked as sent")
c.eq(must(a.post(f"{QT}/{quote['id']}/accept", {"reason": "agreed by phone"}), "accept")["status"], "ACCEPTED", "accepted")
status, body = a.post(f"{QT}/{quote['id']}/convert", {"order_date": today().isoformat()})
c.ok(status in (200, 201), "convert makes the order", f"{status} {message(body)}")
if status in (200, 201):
    again = a.post(f"{QT}/{quote['id']}/convert", {"order_date": today().isoformat()})
    c.refused(again, 422, "already became", "a second convert is refused")
    after = must(a.get(f"{QT}/{quote['id']}"), "quotation read")
    c.ok(after["status"] in ("CONVERTED", "ACCEPTED"), "the quotation records the conversion", after["status"])
    orders = rows_of(a.get(f"{SO}?customer_id={sc.customer['id']}&page_size=50"))
    c.eq(len(orders), 1, "exactly one order exists for the customer")
c.done()
