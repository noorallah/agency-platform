"""Probe: what the sales invoice header's line_discount_total holds when a bill has a line discount and a bill discount.

Prints the fields exactly as the server returns them; the checks only pin the
figures seen on 2026-10-16 so a change is noticed.
"""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sell import *

c = Check("p_sell_line_discount_total")
a = admin()
sc = Scene(a, stock="50")
with counter(a):
    body = sc.bill_body("2", bill_discount_amount="10")
    body["lines"][0]["discount_amount"] = "20"
    made = must(a.post(SI, body), "bill")
    created = {k: v for k, v in made.items() if "discount" in k}
    bill = must(a.post(f"{SI}/{made['id']}/approve", {}), "approve")
bill = must(a.get(f"{SI}/{bill['id']}"), "read")
head = {k: bill[k] for k in bill if "discount" in k}
line = {k: v for k, v in bill["lines"][0].items() if "discount" in k}
print("created header :", created)
print("approved header:", head)
print("line 1         :", line)
print("totals         :", {k: bill[k] for k in ("subtotal", "tax_total", "grand_total")})
c.eq(D(bill["line_discount_total"]), D(30), "header line_discount_total is 30 (line 20 + bill share 10)")
c.eq(D(bill["bill_discount_amount"]), D(10), "header bill_discount_amount is 10")
c.eq(D(bill["lines"][0]["discount_amount"]), D(20), "line discount_amount is 20")
c.done()
