"""Probe (round 7): the goods-receipt import meets the free-goods cap, and a refused file writes nothing (D-BUY-67, D-BUY-73).

An order of 10 with 2 free. A file of two receipts, 5 each, taking 2 and 1 free is refused naming the second
record, and the first is not left behind as a draft. The same file taking 1 and 1 is saved as two drafts; completed,
the shelf holds 12 and a third free unit is refused."""
import json

from _inv import *
from _flow import *

c = Check("p_receipt_import_free")
w = World()
wh = w.warehouse()["id"]
p = w.product()
GR = "/api/v1/goods-receipts"

held = receive(w, wh, p["id"], 10, complete=False, po_line_extra={"free_quantity": "2"},
               line_extra={"current_receipt_quantity": "0", "free_quantity": "0"})
po = held["order"]
line_id = po["lines"][0]["id"]
# the helper's own receipt is only there to raise the order; it brought nothing and is not completed
if held["create"][0] in (200, 201):
    w.admin.post(f"{GR}/{held['receipt']['id']}/cancel", {"reason": "set-up only"})


def record(free: str, qty: str = "5") -> dict[str, Any]:
    """One receipt of the file: ``qty`` of the order line with ``free`` typed as free goods."""
    return {"purchase_order_id": po["id"], "receipt_date": w.today, "lines": [{
        "purchase_order_line_id": line_id, "line_number": 1, "current_receipt_quantity": qty, "free_quantity": free,
        "unit_price": "60", "warehouse_id": wh}]}


def send(*records: dict[str, Any]) -> tuple[int, Any]:
    """Import a file of receipts the way the route reads it (a form field)."""
    return w.admin.upload(f"{GR}/import", "receipts.json", b"{}",
                          fields={"format": "json", "payload": json.dumps({"records": list(records)})})


def live() -> list[dict[str, Any]]:
    """The order's receipts that are not cancelled."""
    st, b = w.admin.get(f"{GR}?purchase_order_id={po['id']}&page_size=50")
    return [r for r in data(b) if r["status"] != "CANCELLED"] if st == 200 else []


before = len(live())
c.eq(before, 0, "the order has no live receipt to begin with")
st, b = send(record("2"), record("1"))
c.ok(st == 422 and "left to give" in message(b), "a file taking 2 and then 1 of the 2 free is refused", (st, message(b)[:240]))
c.ok("Record 2 of 2" in message(b) and "Nothing was imported" in message(b),
     "the refusal names the record and says nothing was imported", message(b)[:240])
c.eq(len(live()), 0, "and the first record was not left behind as a draft")
c.eq(w.qty(p["id"], wh), D(0), "nothing reached the shelf")

st, b = send(record("0"), record("3", qty="0"))
c.ok(st == 422 and "Record 2 of 2" in message(b), "a second record of free goods alone, past the cap, is refused the same way", (st, message(b)[:240]))
c.eq(len(live()), 0, "and again nothing is kept")

st, b = send(record("1"), record("1"))
c.ok(st in (200, 201), "the file taking 1 free on each receipt is imported", (st, message(b)[:240]))
made = data(b) if st in (200, 201) else []
c.eq(len(made), 2, "two receipts came back")
c.eq(len({r["grn_number"] for r in made}), len(made), "each with its own number")
c.eq(len(live()), 2, "and the order shows both")
for r in made:
    c.eq(w.admin.post(f"{GR}/{r['id']}/complete", {})[0], 200, f"{r['grn_number']} is completed")
c.eq(w.qty(p["id"], wh), D(12), "10 bought and 2 free on the shelf")
st, b = send(record("1", qty="0"))
c.ok(st in (409, 422), "with both received, a file of one more free unit is refused", (st, message(b)[:240]))
c.eq(w.qty(p["id"], wh), D(12), "the shelf still holds 12")
c.done()
