"""TC-FIN-014: payment mode and instrument date on receipts and payments; books and the by-mode report."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _col import *

c = Check("tc_col_fin_014")
a = admin()
sc = Scene(a)
cust = sc.customer()
vendor = must(a.post("/api/v1/vendors", {"code": f"CM{sc.tag}", "name": f"Mode vendor {sc.tag}"}), "vendor")
t = today().isoformat()


def by_mode() -> dict[str, dict]:
    """Return the collections-by-mode report keyed by mode, for today."""
    rows = all_rows(a, f"{RC}/reports/collections-by-mode?from_date={t}&to_date={t}")
    return {r["key"]: r for r in rows}


before = by_mode()
chq = data(receipt(a, cust, "111.00", payment_mode="CHEQUE", instrument_reference=f"CHQ{sc.tag}", instrument_date=t)[1])
upi = data(receipt(a, cust, "222.00", payment_mode="UPI")[1])
cash = data(receipt(a, cust, "333.00", method="CASH", payment_mode="CASH")[1])
c.eq((chq["payment_mode"], chq["instrument_reference"], chq["instrument_date"]), ("CHEQUE", f"CHQ{sc.tag}", t), "the cheque receipt keeps its mode, number and date")
c.eq(upi["payment_mode"], "UPI", "the UPI receipt keeps its mode")
c.eq(cash["payment_mode"], "CASH", "the cash receipt keeps its mode")
got = must(a.get(f"{RC}/{chq['id']}"), "read")
c.eq((got["payment_mode"], got["instrument_reference"], got["instrument_date"]), ("CHEQUE", f"CHQ{sc.tag}", t), "and reads back the same")
pay = must(
    a.post("/api/v1/payments", {
        "party_id": vendor["id"], "settlement_date": t, "amount": "70.00", "method": "BANK",
        "payment_mode": "CHEQUE", "instrument_reference": f"PQ{sc.tag}", "instrument_date": t, "allocations": [],
    }),
    "payment",
)
c.eq((pay["payment_mode"], pay["instrument_reference"]), ("CHEQUE", f"PQ{sc.tag}"), "a payment keeps its mode and number")
bank = {r["voucher"]: r for r in all_rows(a, f"/api/v1/finance/reports/bank-book?from_date={t}&to_date={t}", 100)}
cashbook = {r["voucher"]: r for r in all_rows(a, f"/api/v1/finance/reports/cash-book?from_date={t}&to_date={t}", 100)}
row = bank.get(chq["settlement_number"], {})
c.eq(row.get("mode"), "Cheque", "the bank book's Mode column reads Cheque")
c.ok(f"CHQ{sc.tag}" in str(row.get("instrument")), "the Instrument column carries the number", row.get("instrument"))
c.eq(bank.get(upi["settlement_number"], {}).get("mode"), "UPI", "the UPI receipt reads UPI in the bank book")
c.eq(cashbook.get(cash["settlement_number"], {}).get("mode"), "Cash", "the cash receipt reads Cash in the cash book")
c.eq(bank.get(pay["settlement_number"], {}).get("mode"), "Cheque", "the payment's mode is in the bank book")
after = by_mode()


def grew(key: str, field: str, by: str) -> None:
    """Assert one mode's figure moved by exactly this much."""
    was = D(before.get(key, {}).get(field, 0))
    now = D(after.get(key, {}).get(field, 0))
    c.eq(now - was, D(by), f"collections by mode: {key} {field} grew by {by}")


grew("CHEQUE", "collected", "111.00")
grew("UPI", "collected", "222.00")
grew("CASH", "collected", "333.00")
c.done()
