"""TC-SELL-104: a large line typed including GST totals the figure typed."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _sell import *

c = Check("tc_sell_104")
a = admin()
sc = Scene(a, stock="5000")


def incl(qty: str, rate: str, includes: bool = True) -> dict:
    """Raise an order of the item with the switch as given; return it read back."""
    made = new_order(sc, qty, line={"unit_price": rate, "discount_percent": "0"}, rate_includes_tax=includes)
    return must(a.get(f"{SO}/{made['id']}"), "order")


def totals(doc: dict) -> tuple[Decimal, Decimal, Decimal]:
    """Return (taxable, tax, total) of a document."""
    return tuple(D(doc[k]).quantize(D("0.01")) for k in ("subtotal", "tax_total", "grand_total"))  # type: ignore[return-value]


o1 = incl("500", "100")
c.eq(totals(o1), (D("42372.88"), D("7627.12"), D("50000.00")), "step 1: 42,372.88 + 7,627.12 = 50,000.00")
l1 = o1["lines"][0]
c.eq(D(l1["unit_price"]).quantize(D("0.0001")), D("84.7458"), "step 1: 84.7458 before tax")
c.eq(D(l1["entered_rate"]), D(100), "step 1: 100 as typed (entered_rate)")
o2 = incl("1000", "100")
o3 = incl("250", "45.50")
c.eq(D(o2["grand_total"]).quantize(D("0.01")), D("100000.00"), "step 2: 100,000.00")
c.eq(D(o3["grand_total"]).quantize(D("0.01")), D("11375.00"), "step 2: 11,375.00")
q = must(a.post(QT, {
    "customer_id": sc.customer["id"], "quotation_date": today().isoformat(),
    "valid_until": (today() + timedelta(days=15)).isoformat(), "branch_id": sc.branch["id"],
    "warehouse_id": sc.warehouse["id"], "rate_includes_tax": True,
    "lines": [{"line_number": 1, "product_id": sc.product["id"], "quantity": "500", "unit_price": "100", "discount_percent": "0"}]}), "quotation")
c.eq(D(q["grand_total"]).quantize(D("0.01")), D("50000.00"), "step 3: quotation 50,000.00")
o4 = incl("500", "84.7458", includes=False)
c.eq(totals(o4), (D("42372.90"), D("7627.12"), D("50000.02")), "step 4: unchanged, 50,000.02")
for order, want in ((o1, "50000.00"), (o2, "100000.00"), (o3, "11375.00")):
    must(a.post(f"{SO}/{order['id']}/approve", {}), "approve")
    note = new_note(sc, order, order["lines"][0]["quantity"], dispatch=True)
    c.eq(D(note["grand_total"]).quantize(D("0.01")), D(want), f"step 5: the note totals {want}")
    bill = bill_note(sc, note, order["lines"][0]["quantity"])
    c.eq(D(bill["grand_total"]).quantize(D("0.01")), D(want), f"step 5: the bill totals {want}")
    je = journal(a, bill["invoice_number"])
    c.eq([D(e["total_debit"]) for e in je], [D(want)], f"step 5: the bill's journal debits {want}")
o5 = incl("500", "100")
must(a.post(f"{SO}/{o5['id']}/approve", {}), "approve")
note = new_note(sc, o5, "500", dispatch=True)
part = bill_note(sc, note, "200", approve=False)
c.eq(D(part["grand_total"]).quantize(D("0.01")), D("20000.00"), "step 6: the part bill is 20,000.00 before approval")
part = must(a.post(f"{SI}/{part['id']}/approve", {}), "approve")
c.eq(D(part["grand_total"]).quantize(D("0.01")), D("20000.00"), "step 6: and after")
status, raw = a.raw(f"{SI}/{part['id']}/print")
c.ok("20,000.00" in pdf_text(raw) or "20000.00" in pdf_text(raw), "step 6: and prints 20,000.00")
c.done()
