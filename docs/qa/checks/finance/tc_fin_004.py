"""TC-FIN-004: journal entries say which module posted them (server half: source_module and search)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _fin import *

c = Check("tc_fin_004")
a = admin()
sc = Scene(a)
cust = sc.customer()
with counter(a):
    bill = sc.bill(cust, "2")
st, rc = receipt(a, cust, "100.00", [(bill, "100.00")])
c.eq(st, 201, "a 100.00 receipt is recorded")
rcn = data(rc)["settlement_number"]
si = bill["invoice_number"]
dn = next(s["source_document_number"] for s in bill["sources"] if s["source_document_type"] == "DELIVERY_NOTE")  # the note the bill continues; the DN series runs apart from the SI series


def one(search: str) -> dict:
    """The single entry whose reference is exactly the search text."""
    rows = [e for e in rows_of(a.get(f"{JE}?search={search}&page_size=50")) if e["reference_number"] == search]
    c.eq(len(rows), 1, f"searching {search} finds exactly one entry with that reference")
    return rows[0] if rows else {}


for ref, module, words in ((si, "sales_invoice", "Sales invoice"), (dn, "delivery_note", "Cost of goods issued"), (rcn, "settlements", "Receipt")):
    e = one(ref)
    c.eq(e.get("source_module"), module, f"{ref} is posted by {module}")
    c.ok(words in (e.get("description") or ""), f"{ref}'s description reads '{words}'", e.get("description"))
    c.eq(e.get("status"), "POSTED", f"{ref} is POSTED")
    full = entry_by_id(a, e["id"]) if e else {}
    c.eq(full.get("source_module"), module, f"{ref} read singly carries {module} too")
    c.ok(full and balanced(full), f"{ref} balances")
# the description is searchable as well as the reference
by_desc = rows_of(a.get(f"{JE}?search=Cost%20of%20goods%20issued%20on%20{dn}&page_size=50"))
c.ok(any(e["reference_number"] == dn for e in by_desc), "search also matches the description")
# the API (unlike the screen) has a source-module filter
flt = all_rows(a, f"{JE}?source_module=delivery_note")
c.ok(flt and all(e["source_module"] == "delivery_note" for e in flt), "source_module=delivery_note lists only delivery-note entries", len(flt))
c.ok(dn in [e["reference_number"] for e in flt], "and includes this one")
c.done()
