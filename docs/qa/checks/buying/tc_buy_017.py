"""TC-BUY-017: a debit note on a bill already paid.

The case text builds the second bill at 500.00; a bill of whole units at 100 plus
18% GST cannot total 500, so the second bill is 5 x 100 = 590.00 and the expected
balance is 590 - 118 = 472.00 (382.00 in the text for 500.00).
"""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _buy import *

c = Check("tc_buy_017")
a = admin()
sc = Scene(a)
vid = sc.vendor["id"]
order = sc.order()
rc = sc.receive(order, "10")
bill = sc.bill(rc)
c.eq(D(bill["grand_total"]), D(1180), "the first bill is 1,180.00")
c.eq(sc.pay("1180", bill)[0], 201, "paid in full")
order2 = sc.order(qty="5")
bill2 = sc.bill(sc.receive(order2, "5"))
c.eq(D(bill2["grand_total"]), D(590), "the second bill is 590.00")
iline = must(a.get(f"{PI}/{bill['id']}"), "bill")["lines"][0]


def new_note() -> dict:
    """Raise and approve a debit note of 100 taxable on the paid bill."""
    made = must(a.post(DN, {
        "purchase_invoice_id": bill["id"], "debit_note_date": today().isoformat(), "reason": "PRICE_DIFFERENCE",
        "lines": [{"purchase_invoice_line_id": iline["id"], "line_number": 1, "quantity": "0", "taxable_amount": "100"}],
    }), "debit note")
    c.eq(made["status"], "DRAFT", "a new debit note is a draft")
    done = a.post(f"{DN}/{made['id']}/approve", {})
    c.eq(done[0], 200, "approval succeeds on a paid bill")
    return made


note = new_note()


def credit_of(note_id: str) -> dict | None:
    """Find the debit note's row on the supplier-credits list."""
    rows = rows_of(a.get(f"{PAY}/supplier-credits?vendor_id={vid}"))
    return next((r for r in rows if r.get("debit_note_id") == note_id), None)


got = credit_of(note["id"])
c.ok(got is not None, "the credit list holds the debit note")
if got:
    c.eq(D(got["available_amount"]), D(118), "a credit of 118.00")
    c.eq(got["source_type"], "DEBIT_NOTE", "marked as a debit note")
    applied = a.post(f"{PAY}/supplier-credits/{got['source_id']}/apply", {"invoice_id": bill2["id"], "amount": "118"})
    c.ok(applied[0] in (200, 201), "the credit is set against the second bill", (applied[0], message(applied[1])))
    c.eq(owing(a, vid, bill2["id"]), D(472), "the second bill owes 472.00")
    cancel = a.post(f"{DN}/{note['id']}/cancel", {"reason": "check"})
    c.eq(cancel[0], 200, "cancelling the debit note withdraws it")
    c.eq(owing(a, vid, bill2["id"]), D(590), "the second bill owes 590.00 again")
    c.ok(credit_of(note["id"]) is None, "the credit is gone")
    note = new_note()
    got = credit_of(note["id"])
    refund = a.post(f"{PAY}/supplier-credits/{got['source_id']}/refunds", {"amount": "50", "refunded_on": today().isoformat(), "method": "BANK"}) if got else (0, None)
    c.eq(refund[0], 200, "a refund of 50 is recorded")
    c.refused(a.post(f"{DN}/{note['id']}/cancel", {"reason": "check"}), 422, "Reverse that refund", "cancel with a refund standing")
c.done()
