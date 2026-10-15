"""TC-FIN-019: files attached to journals, receipts and payments: a reference held against exactly one document; delete is soft and audited."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _fin import *

c = Check("tc_fin_019")
a = admin()
viewer = admin("viewer")
sc = Scene(a)
cust = sc.customer()
with counter(a):
    bill = sc.bill(cust, "1")
rc = data(receipt(a, cust, "50.00", [(bill, "50.00")])[1])
bsc = buy.Scene(a)
_, _, pbill = bsc.received_and_billed("2")
py = data(bsc.pay("100.00", pbill)[1])
je = data(a.post(JE, draft_body(a, [("5000", "6.00", "0"), ("1000", "0", "6.00")]))[1])
j = data(a.post(f"{JE}/{je['id']}/post", {})[1])
file = {"file_name": f"voucher-{suffix(4)}.pdf", "mime_type": "application/pdf", "file_path": "attachments/voucher.pdf", "caption": "supplier voucher"}
for what, base, doc, key, other in (
    ("journal", f"{FIN}/journal-entries", j, "journal_entry_id", "settlement_id"),
    ("receipt", "/api/v1/receipts", rc, "settlement_id", "journal_entry_id"),
    ("payment", PAY, py, "settlement_id", "journal_entry_id"),
):
    URL = f"{base}/{doc['id']}/attachments"
    c.eq(viewer.post(URL, {"attachments": [file]})[0], 403, f"{what}: a Viewer cannot attach")
    st, ans = a.post(URL, {"attachments": [file]})
    c.ok(st in (200, 201), f"{what}: a file is attached", (st, message(ans)))
    got = data(a.get(URL)[1])
    c.eq(len(got), 1, f"{what}: one file listed")
    if not got:
        continue
    row = got[0]
    c.eq((row["file_name"], row["mime_type"], row["file_path"], row["caption"]), (file["file_name"], "application/pdf", file["file_path"], "supplier voucher"), f"{what}: name, type, path and caption are kept")
    c.eq((row[key], row[other]), (doc["id"], None), f"{what}: held against exactly this one document")
    c.ok(row["created_by"], f"{what}: who added it is kept")
    c.eq(viewer.delete(f"{URL}/{row['id']}")[0], 403, f"{what}: a Viewer cannot delete")
    d = a.delete(f"{URL}/{row['id']}")
    c.ok(d[0] in (200, 204), f"{what}: delete works", d[0])
    c.eq(data(a.get(URL)[1]), [], f"{what}: and the list is empty")
    c.ok(a.delete(f"{URL}/{row['id']}")[0] == 404, f"{what}: deleting it again is 404 (soft-deleted)")
    added = "journal_entry.files_attached" if what == "journal" else "settlement.files_attached"
    c.ok(any(r["entity_id"] == doc["id"] for r in all_rows(a, f"/api/v1/audit-logs?search={added}")), f"{what}: the add is in the firm's audit trail ({added})")
    c.ok(any(r["entity_id"] == row["id"] for r in all_rows(a, "/api/v1/audit-logs?search=ledger_attachment.removed")), f"{what}: the delete is in the firm's audit trail (ledger_attachment.removed)")
# an attachment on a document of another firm's id
other = admin("admin2")
c.eq(other.get(f"{FIN}/journal-entries/{j['id']}/attachments")[0] in (403, 404), True, "another firm cannot list the journal's files")
c.eq(other.post(f"{FIN}/journal-entries/{j['id']}/attachments", {"attachments": [file]})[0] in (403, 404), True, "or add one")
c.done()
