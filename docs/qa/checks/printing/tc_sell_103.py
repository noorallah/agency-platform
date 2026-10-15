"""TC-SELL-103 (print half): a rate typed including GST, what the order, challan and bill print."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from decimal import Decimal

from _prt import *

c = Check("tc_sell_103")
a = admin()
sc = Scene(a, stock="200")
INCL = "Rate incl. GST"


def D(x: object) -> Decimal:  # noqa: N802
    """Return a Decimal."""
    return Decimal(str(x))


def order_pdf(oid: str) -> str:
    """Return the text of an order's print."""
    status, raw = a.raw(f"{SO}/{oid}/print")
    if status != 200:
        raise SystemExit(f"PRECONDITION order print {status} {raw[:150]!r}")
    return pdf_text(raw).replace(chr(10), " ")


if True:
    order, bill = sc.staged_bill("1", "100")
    c.eq(D(bill["grand_total"]), D("118"), "step 1: total 118.00")
    t = pdf_text(printed(a, bill["id"])).replace(chr(10), " ")
    c.ok(INCL not in t, "step 1: the bill has one Rate column")
    c.ok(INCL not in order_pdf(order["id"]), "step 1: the order has one Rate column")

if True:
    order, bill = sc.staged_bill("1", "100", rate_includes_tax=True)
    got = must(a.get(f"{SO}/{order['id']}"), "order")
    c.eq(D(got["grand_total"]), D("100"), "step 2: the order totals 100.00")
    c.eq(D(got["lines"][0]["entered_rate"]), D("100"), "step 2: the order line keeps the rate as typed (entered_rate)")
    ot = order_pdf(order["id"])
    c.ok(INCL in ot, "step 2: the order print has Rate incl. GST", ot[:200])
    c.ok("84.75" in ot, "step 2: the order print has Rate 84.75")
    c.eq(D(bill["grand_total"]), D("100"), "step 2: the bill totals 100.00")
    bt = pdf_text(printed(a, bill["id"])).replace(chr(10), " ")
    c.ok(INCL in bt, "step 2: the bill print has Rate incl. GST (D-SELL-95)")
    c.ok("84.75" in bt and "15.25" in bt, "step 2: the bill print has 84.75 taxable-side rate and 15.25 tax")
    notes = [n for n in all_rows(a, DN) if n.get("sales_order_id") == order["id"]]
    if notes:
        status, raw = a.raw(f"/api/v1/delivery-notes/{notes[0]['id']}/print")
        nt = pdf_text(raw) if status == 200 else ""
        c.ok("84.75" in nt, "step 2: the challan shows Rate 84.75", status)
    else:
        c.ok(False, "step 2: found the delivery note")
    # step 3: a three line order
    five = sc.new_product("F", "100", "50", "GST_5_LOCAL")
    body = {
        "customer_id": sc.customer["id"], "order_date": today().isoformat(),
        "branch_id": sc.branch["id"], "warehouse_id": sc.warehouse["id"],
        "rate_includes_tax": True,
        "lines": [
            {"line_number": 1, "product_id": sc.product["id"], "quantity": "7", "unit_price": "33.33"},
            {"line_number": 2, "product_id": five["id"], "quantity": "3", "unit_price": "105"},
            {"line_number": 3, "product_id": sc.product["id"], "quantity": "1", "unit_price": "99.99"},
        ],
    }
    o3 = must(a.post(SO, body), "order 3")
    c.eq(D(o3["grand_total"]), D("648.30"), "step 3: the order totals 648.30")
    # step 4: discounts
    for line, want, what in (
        ({"quantity": "1", "unit_price": "100", "discount_percent": "10"}, "90", "10% off"),
        ({"quantity": "2", "unit_price": "100", "discount_amount": "20"}, "180", "20 off"),
    ):
        o4 = must(a.post(SO, {**body, "lines": [{"line_number": 1, "product_id": sc.product["id"], **line}]}), "order 4")
        c.eq(D(o4["grand_total"]), D(want), f"step 4: {what} is {want} to pay")
    # step 6: quotation print
    q = must(a.post(QT, {
        "customer_id": sc.customer["id"], "quotation_date": today().isoformat(),
        "valid_until": today().isoformat(), "branch_id": sc.branch["id"],
        "warehouse_id": sc.warehouse["id"], "rate_includes_tax": True,
        "lines": [{"line_number": 1, "product_id": sc.product["id"], "quantity": "1", "unit_price": "100"}]}), "quotation")
    c.eq(D(q["grand_total"]), D("100"), "step 6: the quotation totals 100.00")
    status, raw = a.raw(f"{QT}/{q['id']}/print")
    c.eq(status, 200, "step 6: the quotation prints")
    c.ok(INCL in pdf_text(raw).replace(chr(10), " "), "step 6: the quotation prints both rates")
c.done()
