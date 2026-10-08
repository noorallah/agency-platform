"""Probe (round 8): a file of purchase bills refused at its second record writes nothing (D-BUY-73, the bill third).

Six received. A file of two bills whose second takes nine is refused, the refusal names the second record, and the
first is not left behind as a draft. Two and two is saved as two drafts; with two left, two and then one is refused
whole, and one and one is saved. (A supplier bill number given twice is a warning on the bill, not a refusal.)"""
import json

from _inv import *
from _flow import *

c = Check("p_bill_import_refused")
w = World()
wh = w.warehouse()["id"]
p = w.product()
GR = "GOODS_RECEIPT"
got = receive(w, wh, p["id"], 6)
c.ok(got.get("status", (0,))[0] == 200, "six are ordered and received", got.get("status"))
grn = must(w.admin.get(f"/api/v1/goods-receipts/{got['receipt']['id']}"), "read receipt")
PI = "/api/v1/purchase-invoices"


def record(number: str, qty: str = "2") -> dict[str, Any]:
    """One bill of the file: ``qty`` of the receipt's line under this supplier bill number."""
    return {"invoice_date": w.today, "supplier_invoice_number": number, "supplier_invoice_date": w.today,
            "source_documents": [{"source_document_type": GR, "source_document_id": grn["id"]}],
            "lines": [{"source_document_type": GR, "source_document_id": grn["id"],
                       "source_document_line_id": grn["lines"][0]["id"], "line_number": 1,
                       "current_invoice_quantity": qty}]}


def send(*records: dict[str, Any]) -> tuple[int, Any]:
    """Import a file of bills the way the route reads it (a form field)."""
    return w.admin.upload(f"{PI}/import", "bills.json", b"{}",
                          fields={"format": "json", "payload": json.dumps({"records": list(records)})})


def live() -> list[dict[str, Any]]:
    """The supplier's bills that are not cancelled."""
    st, b = w.admin.get(f"{PI}?vendor_id={w.vendor_id}&page_size=50")
    return [r for r in data(b) if r["status"] != "CANCELLED"] if st == 200 else []


one, two = f"SB-{w.tag}-1", f"SB-{w.tag}-2"
c.eq(len(live()), 0, "the supplier has no bill to begin with")
st, b = send(record(one), record(two, "9"))
c.ok(st in (409, 422) and "left to bill" in message(b), "a file whose second bill takes more than was received is refused", (st, message(b)[:240]))
c.ok("Record 2 of 2" in message(b) and "Nothing was imported" in message(b),
     "the refusal names the record and says nothing was imported", message(b)[:240])
c.eq(len(live()), 0, "and the first record was not left behind as a draft")
st, b = send(record(one), record(two))
c.ok(st in (200, 201), "the file billing two and two is imported", (st, message(b)[:240]))
made = data(b) if st in (200, 201) else []
c.eq(len(made), 2, "two bills came back")
c.eq(len({r["invoice_number"] for r in made}), len(made), "each with its own number")
c.eq(len(live()), 2, "and the supplier shows both")
c.eq({r["status"] for r in made}, {"DRAFT"}, "both are drafts")
st, b = send(record(f"SB-{w.tag}-3"), record(f"SB-{w.tag}-4", "1"))
c.ok(st in (409, 422) and "Record 2 of 2" in message(b), "with two left to bill, a file of two and then one is refused at its second record", (st, message(b)[:240]))
c.eq(len(live()), 2, "and its first bill is not kept")
st, b = send(record(f"SB-{w.tag}-3", "1"), record(f"SB-{w.tag}-4", "1"))
c.ok(st in (200, 201), "one and one fits what is left", (st, message(b)[:240]))
c.eq(len(live()), 4, "four bills cover the six received")
c.done()
