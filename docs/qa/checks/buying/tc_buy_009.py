"""TC-BUY-009: a return the supplier pays back (refund)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _buy import *

c = Check("tc_buy_009")
a = admin()
sc = Scene(a)
order = sc.order()
sc.receive(order, "4")
r6 = sc.receive(order, "6")
bill = sc.bill(r6)
c.eq(sc.pay("708", bill)[0], 201, "the bill is paid in full first")
ret = sc.ret(r6, "2", outcome="REFUND")
c.eq(ret["outcome"], "REFUND", "the return's outcome is Refund")
c.eq(D(ret["grand_total"]), D(236), "2 x 100 + 18% = 236.00")
RF = f"{PAY}/supplier-credits/{ret['id']}/refunds"


def credit() -> dict:
    """Read the return's row from the supplier-credits list."""
    rows = rows_of(a.get(f"{PAY}/supplier-credits?vendor_id={sc.vendor['id']}"))
    return next(r for r in rows if r["purchase_return_id"] == ret["id"])


c.eq(D(credit()["available_amount"]), D(236), "the credit shows 236.00 available")
day = today().isoformat()
made = a.post(RF, {"amount": "100", "refunded_on": day, "method": "BANK"})
c.eq(made[0], 200, "a refund of 100 is recorded")
c.eq(D(credit()["refunded_amount"]), D(100), "Refunded reads 100")
c.eq(D(credit()["available_amount"]), D(136), "Available is reduced by 100")
if made[0] == 200:
    entry = data(made[1])["journal_entry_id"]
    c.ok(bool(entry), "the refund posted a journal entry")
c.refused(a.post(RF, {"amount": "1000", "refunded_on": day, "method": "BANK"}), 422, "136.00", "over-refund names what is left")
c.refused(a.post(RF, {"amount": "10", "refunded_on": (today() + timedelta(days=1)).isoformat(), "method": "BANK"}), 422, "future date", "a refund dated tomorrow")
c.refused(a.post(RF, {"amount": "10", "refunded_on": (today() - timedelta(days=1)).isoformat(), "method": "BANK"}), 422, "on or after the return", "a refund dated before the return")
c.refused(a.post(f"{PR}/{ret['id']}/cancel", {"reason": "x"}), 422, "Reverse the refund first", "cancelling the return while a refund stands")
if made[0] == 200:
    rev = a.post(f"{PAY}/supplier-credits/refunds/{data(made[1])['id']}/reverse", {"reason": "check"})
    c.eq(rev[0], 200, "the refund is reversed")
    c.eq(D(credit()["available_amount"]), D(236), "after Reverse the credit is whole again")
    if rev[0] == 200:
        c.ok(bool(data(rev[1]).get("reversal_journal_entry_id")), "the mirror journal posted", data(rev[1]))
c.done()
