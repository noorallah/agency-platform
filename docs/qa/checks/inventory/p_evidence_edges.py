"""Probe (round 10): evidence files at the edges (STK-9).

A file sent with a request is kept with the movement its approval posts, a
refused post keeps no file, a name of only spaces is refused, the ten-file
cap is the cap on what a movement holds, and a count that was cancelled
keeps what it had.
"""
import uuid

from _inv import *
from _flow import *

c = Check("p_evidence_edges")
w = World()
wh = w.warehouse()
p = w.product()
w.stock_in(wh["id"], p["id"], 50)
REQ = f"{INV}/adjustment-requests"
base = {"branch_id": w.branch_id, "warehouse_id": wh["id"], "product_id": p["id"], "transaction_date": w.today}


def att(name: str, count: int = 1) -> list[dict]:
    """Attachment payloads."""
    return [{"file_name": f"{i}{name}", "mime_type": "image/jpeg", "file_path": f"evidence/{w.tag}/{i}{name}"} for i in range(count)]


def files_of(kind: str) -> tuple[str, list[str]]:
    """The newest movement of a kind, and the files it holds."""
    tx = [x for x in w.ledger(p["id"]) if x["transaction_type"] == kind][-1]
    st, b = w.admin.get(f"{INV}/transactions/{tx['transaction_id']}/attachments")
    return tx["transaction_id"], [f["file_name"] for f in data(b)]


# a request's file arrives with the movement
st, b = w.admin.post(REQ, {"kind": "WRITE_OFF", "write_off": {**base, "quantity": "2", "reason": "DAMAGE", "attachments": att("req.jpg")}})
c.eq(st, 201, "a request with a file is accepted")
if st == 201:
    st, b = w.admin.post(f"{REQ}/{data(b)['id']}/approve", {})
    c.eq(st, 200, "and approved")
    tx, names = files_of("WRITE_OFF")
    c.eq(names, ["0req.jpg"], "the file is on the movement the approval posted")

# a refused post keeps nothing
before = len(w.ledger(p["id"]))
st, b = w.admin.post(f"{INV}/write-offs", {**base, "quantity": "9999", "reason": "DAMAGE", "attachments": att("no.jpg")})
c.eq(st, 422, "a write-off of more than is held is refused")
c.eq(len(w.ledger(p["id"])), before, "and wrote no movement")

# names
for label, item in (
    ("a name of only spaces", {"file_name": "   ", "file_path": "e/x.jpg"}),
    ("a path of only spaces", {"file_name": "x.jpg", "file_path": "   "}),
    ("no path", {"file_name": "x.jpg"}),
    ("an unknown field", {"file_name": "x.jpg", "file_path": "e/x.jpg", "size": 3}),
):
    st, b = w.admin.post(f"{INV}/transactions/{tx}/attachments", {"attachments": [item]})
    c.eq(st, 422, f"{label} is refused")
tx, names = files_of("WRITE_OFF")
c.eq(names, ["0req.jpg"], "none of the refused files was kept")

# ten at once is the most; eleven is refused
st, b = w.admin.post(f"{INV}/transactions/{tx}/attachments", {"attachments": att("many.jpg", 11)})
c.eq(st, 422, "eleven files in one go are refused")
st, b = w.admin.post(f"{INV}/transactions/{tx}/attachments", {"attachments": att("nine.jpg", 9)})
c.ok(st in (200, 201), "nine more make ten", (st, message(b)))
st, b = w.admin.post(f"{INV}/transactions/{tx}/attachments", {"attachments": att("over.jpg")})
c.eq(st, 422, "an eleventh on the same movement is refused")
c.eq(len(files_of("WRITE_OFF")[1]), 10, "the movement holds ten")

# nothing to attach, nowhere to attach
st, b = w.admin.post(f"{INV}/transactions/{tx}/attachments", {"attachments": []})
c.eq(st, 422, "an empty list is refused")
ghost = uuid.uuid4()
st, b = w.admin.post(f"{INV}/transactions/{ghost}/attachments", {"attachments": att("g.jpg")})
c.eq(st, 404, "an unknown movement is not found")
st, b = w.admin.delete(f"{INV}/attachments/{ghost}")
c.eq(st, 404, "an unknown file is not found")
st, b = w.admin.get(f"{INV}/counts/{ghost}/attachments")
c.eq(st, 404, "an unknown count is not found")

# a cancelled count keeps its files and takes no more
cnt = must(w.admin.post(f"{INV}/counts", {"branch_id": w.branch_id, "warehouse_id": wh["id"], "count_date": w.today}), "count")
st, b = w.admin.post(f"{INV}/counts/{cnt['id']}/attachments", {"attachments": att("sheet.jpg")})
c.ok(st in (200, 201), "a draft count takes a file", (st, message(b)))
st, b = w.admin.post(f"{INV}/counts/{cnt['id']}/cancel", {"reason": "probe"})
c.eq(st, 200, "the count is cancelled")
st, b = w.admin.get(f"{INV}/counts/{cnt['id']}/attachments")
c.eq([f["file_name"] for f in data(b)] if st == 200 else st, ["0sheet.jpg"], "its file is still listed")
c.done()
