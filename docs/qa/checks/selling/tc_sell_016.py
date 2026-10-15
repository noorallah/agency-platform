"""TC-SELL-016: a credit note reverses the tax the line was charged, and no more than the line."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sell import *

c = Check("tc_sell_016")
a = admin()
sc = Scene(a, stock="100")
order = new_order(sc, "12", approve=True, line={"unit_price": "84", "discount_percent": "2.5"})
note = new_note(sc, order, "5", dispatch=True)
bill = bill_note(sc, note, "5")
line = must(a.get(f"{SI}/{bill['id']}"), "bill")["lines"][0]


def body(amount: str) -> dict:
    """Return a credit-note body for the first line."""
    return {"sales_invoice_id": bill["id"], "credit_note_date": today().isoformat(),
            "reason": "RATE_DIFFERENCE",
            "lines": [{"sales_invoice_line_id": line["id"], "line_number": 1, "taxable_amount": amount}]}


made = must(a.post(CN, body("50")), "credit note 50")
c.eq(D(made["total_amount"]), D("59"), "59.00 in all")
c.eq(D(made["tax_amount"]), D("9"), "tax 9.00")
before = owed(a, sc.customer["id"])
ok = must(a.post(f"{CN}/{made['id']}/approve", {}), "approve")
c.eq(ok["status"], "APPROVED", "approved")
c.eq(before - owed(a, sc.customer["id"]), D("59"), "outstanding down 59")
big = a.post(CN, body("400"))
c.refused(big, 422, "cannot credit more than the line was charged", "400 more is refused")
c.ok("409.50" in message(big[1]) and "50.00" in message(big[1]), "naming charged and credited", message(big[1]))
c.done()
