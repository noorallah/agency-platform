"""TC-SELL-027: several delivery notes on one bill, and the salesman clash."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sell import *

c = Check("tc_sell_027")
a = admin()
sc = Scene(a, stock="200")
s1, s2 = salesman(a, sc.tag), salesman(a, sc.tag)
notes = []
for who, qty in ((s1, "5"), (s1, "7"), (s2, "3")):
    order = new_order(sc, qty, approve=True, salesman_id=who["id"])
    notes.append(new_note(sc, order, qty, dispatch=True))


def body(chosen: list[dict]) -> dict:
    """Return one bill of the chosen notes, billing each line in full."""
    lines = []
    for number, note in enumerate(chosen, 1):
        full = must(a.get(f"{DN}/{note['id']}"), "note")["lines"][0]
        lines.append({"source_document_type": "DELIVERY_NOTE", "source_document_id": note["id"],
                      "source_document_line_id": full["id"], "line_number": number,
                      "current_invoice_quantity": full["current_delivery_quantity"]})
    return {"customer_id": sc.customer["id"], "branch_id": sc.branch["id"],
            "invoice_date": today().isoformat(),
            "source_documents": [{"source_document_type": "DELIVERY_NOTE", "source_document_id": n["id"]} for n in chosen],
            "lines": lines}


clash = a.post(SI, body([notes[0], notes[2]]))
c.refused(clash, 422, "same salesman", "notes of two salesmen cannot share a bill")
one = a.post(SI, body([notes[0], notes[1]]))
c.eq(one[0], 201, f"two notes of one salesman make one bill ({message(one[1])})")
if one[0] == 201:
    bill = data(one[1])
    c.eq(len(bill["lines"]), 2, "two lines")
    c.eq(D(bill["total_current_invoice_quantity"]), D(12), "12 billed")
    c.eq(len(bill["sources"]), 2, "two sources")
    c.eq(bill["salesman_id"], s1["id"], "the bill names the salesman")
    again = a.post(SI, body([notes[0]]))
    c.ok(again[0] >= 400, "a note already on a draft bill cannot be billed twice", again[0])
alone = a.post(SI, body([notes[2]]))
c.eq(alone[0], 201, f"the third note alone is billable ({message(alone[1])})")
c.done()
