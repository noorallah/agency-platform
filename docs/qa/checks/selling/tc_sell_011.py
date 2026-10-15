"""TC-SELL-011: billing a note: the cap, the approval and its journal."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sell import *

c = Check("tc_sell_011")
a = admin()
sc = Scene(a, stock="100")
order = new_order(sc, "12", approve=True, line={"unit_price": "84", "discount_percent": "2.5"})
note = new_note(sc, order, "5", dispatch=True)
nl = must(a.get(f"{DN}/{note['id']}"), "note")["lines"][0]
body = {
    "customer_id": sc.customer["id"], "branch_id": sc.branch["id"],
    "invoice_date": today().isoformat(),
    "source_documents": [{"source_document_type": "DELIVERY_NOTE", "source_document_id": note["id"]}],
    "lines": [{"source_document_type": "DELIVERY_NOTE", "source_document_id": note["id"],
               "source_document_line_id": nl["id"], "line_number": 1, "current_invoice_quantity": "6"}],
}
over = a.post(SI, body)
c.refused(over, 422, "exceeds the available source quantity", "6 against a note of 5 is refused")
body["lines"][0]["current_invoice_quantity"] = "5"
made = must(a.post(SI, body), "bill 5")
c.eq(made["status"], "DRAFT", "created as a draft")
c.eq(owed(a, sc.customer["id"]), D(0), "a draft owes nothing")
bill = must(a.post(f"{SI}/{made['id']}/approve", {}), "approve")
c.eq(bill["status"], "APPROVED", "approved")
c.eq(D(bill["grand_total"]), D("483.21"), "total 483.21")
entries = journal(a, bill["invoice_number"])
c.eq(len(entries), 1, "one journal entry for the bill")
if entries:
    lines = entries[0]["lines"]
    c.eq(sorted(D(l["debit_amount"]) for l in lines if D(l["debit_amount"])), [D("483.21")], "Dr receivables 483.21 alone")
    c.eq(sorted(D(l["credit_amount"]) for l in lines if D(l["credit_amount"])), [D("36.85"), D("36.86"), D("409.50")], "Cr sales 409.50, CGST 36.86, SGST 36.85")
c.eq(owed(a, sc.customer["id"]), D("483.21"), "the customer owes 483.21")
c.done()
