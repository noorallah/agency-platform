"""TC-STOCK-015: evidence attached to adjustments, write-offs, transfers and counts."""
from _inv import *
from _flow import *

c = Check("tc_stock_015")
w = World()
w1, w2 = w.warehouse("A"), w.warehouse("B")
p = w.product()
w.stock_in(w1["id"], p["id"], 20)


def att(name: str) -> list[dict]:
    """One attachment payload."""
    return [{"file_name": name, "mime_type": "image/jpeg", "file_path": f"evidence/{w.tag}/{name}", "caption": name}]


base = {"branch_id": w.branch_id, "warehouse_id": w1["id"], "product_id": p["id"], "transaction_date": w.today}
c.eq(w.admin.post(f"{INV}/adjustments", {**base, "quantity": "-1", "reference_number": f"A{w.tag}", "reason_code": "LOSS",
                                         "attachments": att("adj.jpg")})[0], 201, "adjustment with a file")
c.eq(w.admin.post(f"{INV}/write-offs", {**base, "quantity": "1", "reason": "DAMAGE", "reference_number": f"W{w.tag}",
                                        "attachments": att("wo.jpg")})[0], 201, "write-off with a file")
tbase = {k: v for k, v in base.items() if k != "warehouse_id"}
c.eq(w.admin.post(f"{INV}/transfers", {**tbase, "from_warehouse_id": w1["id"], "to_warehouse_id": w2["id"],
                                       "quantity": "2", "reference_number": f"T{w.tag}",
                                       "attachments": att("trf.jpg")})[0], 201, "transfer with a file")
led = w.ledger(p["id"])
files = {}
for kind in ("ADJUSTMENT", "WRITE_OFF", "TRANSFER_OUT", "TRANSFER_IN"):
    tx = [x for x in led if x["transaction_type"] == kind][-1]
    st, b = w.admin.get(f"{INV}/transactions/{tx['transaction_id']}/attachments")
    files[kind] = [f["file_name"] for f in data(b)] if st == 200 else (st, message(b))
c.eq(files["ADJUSTMENT"], ["adj.jpg"], "adjustment evidence readable")
c.eq(files["WRITE_OFF"], ["wo.jpg"], "write-off evidence readable")
c.eq(files["TRANSFER_OUT"], ["trf.jpg"], "transfer files sit on the outbound leg")
c.eq(files["TRANSFER_IN"], ["trf.jpg"], "and are readable from the inbound leg")
# a posted count still takes files
cnt = must(w.admin.post(f"{INV}/counts", {"branch_id": w.branch_id, "warehouse_id": w1["id"], "count_date": w.today}), "count")
must(w.admin.put(f"{INV}/counts/{cnt['id']}", {"lines": [{"product_id": p["id"], "counted_quantity": "16"}]}), "count a line")
must(w.admin.post(f"{INV}/counts/{cnt['id']}/post", {}), "post count")
st, b = w.admin.post(f"{INV}/counts/{cnt['id']}/attachments", {"attachments": att("sheet.pdf")})
c.ok(st in (200, 201), "a posted count takes a file", (st, message(b)))
st, b = w.admin.get(f"{INV}/counts/{cnt['id']}/attachments")
rows = data(b)
c.eq([f["file_name"] for f in rows], ["sheet.pdf"], "count evidence listed")
# delete is soft and audited
if rows:
    st, b = w.admin.delete(f"{INV}/attachments/{rows[0]['id']}")
    c.eq(st, 204, "delete accepted")
    st, b = w.admin.get(f"{INV}/counts/{cnt['id']}/attachments")
    c.eq(data(b), [], "deleted file no longer listed")
    acts = {a["action"] for a in w.audit(entity_id=cnt["id"])}
    c.ok("inventory.evidence_removed" in acts, "the delete is in the audit trail", acts)
c.done()
