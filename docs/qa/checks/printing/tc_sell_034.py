"""TC-SELL-034: the UPI ID is validated and the bill prints a QR for what it still owes."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _prt import *

c = Check("tc_sell_034")
a = admin()
sc = Scene(a, stock="50")
held = must(a.get(PRINT_TEMPLATE), "template")
base = {k: v for k, v in held.items() if k not in ("id", "document_type", "is_customised")}
status, body = a.put(PRINT_TEMPLATE, {**base, "upi_id": "shop"})
c.eq(status, 422, "a UPI ID with no @ is refused")
c.ok("UPI" in message(body) or "@" in message(body), "the refusal says what a UPI ID looks like", message(body))


def lower(raw: bytes) -> str:
    """Return the lowercased text of a print."""
    return pdf_text(raw).lower()


QR = "scan to pay by upi"
with counter(a):
    bill = sc.bill()
    draft = sc.bill(approve=False)
    total = float(bill["grand_total"])
    with template(a, upi_id="shop@upi"):
        c.eq(data(a.get(PRINT_TEMPLATE)[1])["upi_id"], "shop@upi", "the UPI ID reads back")
        t = lower(printed(a, bill["id"]))
        c.ok(QR in t, "A4: an owing bill prints Scan to pay by UPI", t[-300:])
        c.ok("shop@upi" in t, "A4: the UPI ID is beside the code")
        c.ok(f"{total:.2f}" in t, "A4: the amount owing is printed")
        c.ok(QR not in lower(printed(a, draft["id"])), "a draft bill prints no QR")
        for size in ("HALF", "THERMAL80"):
            with template(a, upi_id="shop@upi", page_size=size):
                t2 = lower(printed(a, bill["id"]))
                c.ok(QR in t2, f"{size}: the QR is there")
                c.ok("shop@upi" in t2, f"{size}: the UPI ID is there")
        half = round(total / 2, 2)
        rest = round(total - half, 2)
        must(a.post("/api/v1/receipts", {
            "party_id": sc.customer["id"], "settlement_date": today().isoformat(),
            "amount": f"{half:.2f}", "method": "CASH",
            "allocations": [{"invoice_id": bill["id"], "amount": f"{half:.2f}"}]}), "part receipt")
        t = lower(printed(a, bill["id"]))
        c.ok(QR in t, "part paid: still prints")
        c.ok(f"{rest:.2f}" in t, f"part paid: asks only for the rest {rest:.2f}")
        must(a.post("/api/v1/receipts", {
            "party_id": sc.customer["id"], "settlement_date": today().isoformat(),
            "amount": f"{rest:.2f}", "method": "CASH",
            "allocations": [{"invoice_id": bill["id"], "amount": f"{rest:.2f}"}]}), "rest")
        c.ok(QR not in lower(printed(a, bill["id"])), "paid: no QR")
    c.ok(QR not in lower(printed(a, bill["id"])), "no UPI ID saved: no QR on any bill")
c.done()
