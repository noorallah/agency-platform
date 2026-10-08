"""Probe (round 8): opening stock sent as JSON and posted in one go leaves nothing behind when the posting is refused (D-STK-56).

Ten of a product arrive by `POST /inventory/opening-stock/import`. The same item again under a new number is refused
at posting; no draft is left holding that number, so the corrected payload (another product) goes in under it."""
import json

from _inv import *
from _flow import *

c = Check("p_opening_import_json")
w = World()
wh = w.warehouse()["id"]
p1, p2 = w.product(), w.product()
IMP = f"{INV}/opening-stock/import"


def send(reference: str, product_id: str, qty: str = "10", auto_post: bool = True) -> tuple[int, Any]:
    """Import one opening-stock document the way the route reads it (a form field)."""
    body = {"reference_number": reference, "posting_date": w.today, "branch_id": w.branch_id, "warehouse_id": wh,
            "auto_post": auto_post, "lines": [{"product_id": product_id, "quantity": qty, "unit_cost": "5"}]}
    return w.admin.upload(IMP, "os.json", b"{}", fields={"format": "json", "payload": json.dumps(body)})


def documents(reference: str) -> list[dict[str, Any]]:
    """The firm's opening-stock documents carrying this number."""
    st, b = w.admin.get(f"{INV}/opening-stock?search={reference}&page_size=50")
    return [r for r in data(b) if r["reference_number"] == reference] if st == 200 else []


first, again = f"OSJ-{w.tag}-A", f"OSJ-{w.tag}-B"
st, b = send(first, p1["id"])
c.ok(st in (200, 201) and data(b)["status"] == "POSTED", "the first import is saved and posted", (st, message(b)[:200]))
c.eq(w.qty(p1["id"], wh), D(10), "ten on the shelf")
st, b = send(again, p1["id"])
c.ok(st == 422 and "already has posted opening stock" in message(b), "the same item again is refused at posting", (st, message(b)[:240]))
c.eq(len(documents(again)), 0, "and no draft is left under the refused number")
c.eq(w.qty(p1["id"], wh), D(10), "the shelf still holds ten")
st, b = send(again, p2["id"], qty="4")
c.ok(st in (200, 201) and data(b)["status"] == "POSTED", "the corrected payload goes in under the same number", (st, message(b)[:240]))
c.eq(w.qty(p2["id"], wh), D(4), "four of the other product arrive")
st, b = send(again, p2["id"])
c.ok(st in (409, 422), "a number already used is refused", (st, message(b)[:200]))
c.eq(len(documents(again)), 1, "and stays one document")
st, b = send(f"OSJ-{w.tag}-C", p2["id"], auto_post=False)
c.ok(st in (200, 201) and data(b)["status"] == "DRAFT", "without auto_post the import is kept as a draft", (st, message(b)[:200]))
c.eq(w.qty(p2["id"], wh), D(4), "and a draft stocks nothing")
st, b = w.admin.upload(IMP, "os.json", b"{}", fields={"format": "json", "payload": "{not json"})
c.ok(st == 422, "a payload that is not JSON is a 422, not a 500", (st, message(b)[:160]))
c.done()
