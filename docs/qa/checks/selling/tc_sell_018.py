"""TC-SELL-018: why the goods go out, and dispatch before the invoice."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sell import *

c = Check("tc_sell_018")
a = admin()
sc = Scene(a, stock="100")
pid = sc.product["id"]
order = new_order(sc, "20", approve=True)


def approved(qty: str, **extra: object) -> dict:
    """Raise and approve a note of the order."""
    made = new_note(sc, order, qty, **extra)
    return must(a.post(f"{DN}/{made['id']}/approve", {}), "note approve")


with gst_policy(a, dispatch_without_invoice="WARN"):
    n = approved("2", challan_reason="SALE")
    done = a.post(f"{DN}/{n['id']}/dispatch", {})
    c.eq(done[0], 200, f"under WARN a Sale note dispatches ({message(done[1])})")
    n = approved("2", challan_reason="ON_APPROVAL")
    c.eq(a.post(f"{DN}/{n['id']}/dispatch", {})[0], 200, "supply on approval dispatches")
with gst_policy(a, dispatch_without_invoice="BLOCK"):
    n = approved("2", challan_reason="SALE")
    blocked = a.post(f"{DN}/{n['id']}/dispatch", {})
    c.refused(blocked, 422, "tax invoice", "under BLOCK a Sale note is refused")
    c.eq(must(a.get(f"{DN}/{n['id']}"), "note")["status"], "APPROVED", "the refused note stays approved")
    c.eq(stock(a, pid)[0], D(96), "nothing left for the refused note")
    both = a.post(f"{DN}/{n['id']}/dispatch-and-invoice", {})
    c.eq(both[0], 200, f"dispatch-and-invoice goes through ({message(both[1])})")
    if both[0] == 200:
        inv = data(both[1])
        c.eq(inv["status"], "APPROVED", "the bill is approved in the same step")
        c.eq(must(a.get(f"{DN}/{n['id']}"), "note")["status"], "DISPATCHED", "and the note is dispatched")
    n = approved("2", challan_reason="ON_APPROVAL")
    c.eq(a.post(f"{DN}/{n['id']}/dispatch", {})[0], 200, "supply on approval is free under BLOCK")
    n = approved("2", challan_reason="ROUTE_SALE")
    c.eq(a.post(f"{DN}/{n['id']}/dispatch", {})[0], 200, "a route sale is free unless the firm says otherwise")
other = a.post(DN, {
    "sales_order_id": order["id"], "delivery_date": today().isoformat(),
    "challan_reason": "OTHER",
    "lines": [{"sales_order_line_id": order["lines"][0]["id"], "line_number": 1, "current_delivery_quantity": "1"}]})
c.refused(other, 422, "say why", "Other without words is refused")
c.done()
