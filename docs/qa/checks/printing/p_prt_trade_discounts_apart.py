"""Probe: the Trade bill prints the line discounts and the discount on the bill as two figures that add up.

No PDF library is installed, so the text is read with ``pdf_text`` and the sum is
checked from the figures the API gives for the same bill.
"""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from decimal import Decimal

from _prt import *

c = Check("p_prt_trade_discounts_apart")
a = admin()
scene = Scene(a)


def m(x: object) -> str:
    """Return a figure as the print shows it."""
    return f"{Decimal(str(x)):,.2f}"


with counter(a):
    body = scene.bill_body("2", bill_discount_amount="10")
    body["lines"][0]["discount_amount"] = "20"
    made = must(a.post(SI, body), "bill")
    bill = must(a.post(f"{SI}/{made['id']}/approve", {}), "approve")
bill = must(a.get(f"{SI}/{bill['id']}"), "read")
# The header's line_discount_total reads 30 here (the 20 plus the bill's 10
# share); the lines' own discount_amount is the 20 the print shows apart.
line_disc = sum((Decimal(str(x["discount_amount"])) for x in bill["lines"]), Decimal("0"))
bill_disc = Decimal(str(bill["bill_discount_amount"]))
tax = Decimal(str(bill["tax_total"]))
c.eq((line_disc, bill_disc), (Decimal("20"), Decimal("10")), "the API holds 20 off the line and 10 off the bill")
taxable = Decimal(str(bill["subtotal"]))
gross = taxable + line_disc + bill_disc
c.eq(gross, Decimal("200"), "gross less both discounts is the taxable value (200 - 20 - 10)")
try:
    with template(a, bill_layout="TRADE", page_size="A4"):
        text = pdf_text(printed(a, bill["id"]))
    for label in ("Gross", "Line discounts", "Discount on bill", "Taxable value"):
        c.ok(label in text, f"Trade print shows {label}", text[:200])
    for figure, what in ((gross, "gross"), (line_disc, "line discounts"), (bill_disc, "discount on bill"), (taxable, "taxable value")):
        c.ok(m(figure) in text, f"Trade print shows the {what} figure {m(figure)}")
    with template(a, page_size="HALF"):
        half = pdf_text(printed(a, bill["id"]))
    c.ok("Discount on bill" in half, "half page shows Discount on bill")
    c.ok(m(tax / 2) in half or m(tax) in half, f"half page carries the bill's tax {m(tax)} (or each half {m(tax / 2)})")
finally:
    pass  # the template context managers put the firm's settings back
c.done()
