"""TC-FIN-015 (server half): bank details on documents, masking, and the cheque leaf."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _col import *

c = Check("tc_col_fin_015")
a = admin()
viewer = admin("viewer")
cashier = admin("cashier")
accounts = {x["name"]: x for x in rows_of(a.get("/api/v1/finance/ledger-accounts"))}
bank, petty, payable = accounts["Bank"], accounts["Petty Cash"], accounts["Trade Payables"]
details = {
    "bank_name": "HDFC Bank", "account_name": "Check Firm", "account_number": "123456789012",
    "ifsc": "HDFC0001234", "branch": "Main Road", "upi_id": "check@hdfc", "print_on_documents": True,
}
path = f"/api/v1/finance/bank-details/{bank['id']}"
try:
    put = a.put(path, details)
    c.eq(put[0], 200, "the bank account's details are saved")
    got = data(put[1])
    c.eq(got["account_number"], "123456789012", "the administrator reads the full number")
    c.eq(got["print_on_documents"], True, "marked to print")
    seen = data(viewer.get(path)[1])
    c.eq(seen["account_number"], "XXXXXXXX9012", "a Viewer reads the last four only")
    c.eq(seen["masked"], True, "and the answer says it is masked")
    full = data(cashier.get(path)[1])
    c.eq(full["account_number"], "123456789012", "a Cashier (PAYMENT_CREATE) reads the full number")
    second = a.put(f"/api/v1/finance/bank-details/{petty['id']}", {**details, "account_number": "999900001111"})
    c.eq(second[0], 200, "a second account can be marked to print (the mark moves to it)")
    marked = [r["ledger_account_code"] for r in rows_of(a.get("/api/v1/finance/bank-details")) if r["print_on_documents"]]
    c.eq(marked, ["1005"], "at most one account is marked: only the second now prints")
    liab = a.put(f"/api/v1/finance/bank-details/{payable['id']}", {**details, "print_on_documents": False})
    c.ok(liab[0] in (409, 422), "details on a liability account are refused", liab[0])
    c.eq(viewer.put(path, details)[0], 403, "a Viewer cannot save details")
    # cheque layout
    lay = a.put(f"/api/v1/payments/cheque-layouts/{bank['id']}", {"offset_x_mm": "2.5", "offset_y_mm": "-1.5", "print_ac_payee": True})
    c.eq(lay[0], 200, "the cheque layout offsets are saved")
    c.eq((D(data(lay[1])["offset_x_mm"]), D(data(lay[1])["offset_y_mm"])), (D("2.5"), D("-1.5")), "and read back exactly")
    status, raw = a.raw(f"/api/v1/payments/cheque-layouts/{bank['id']}/test")
    c.eq((status, raw[:4]), (200, b"%PDF"), "Test print gives a PDF")
    # payments
    vendor = must(a.post("/api/v1/vendors", {"code": f"CK{suffix(5)}", "name": "Cheque vendor"}), "vendor")
    t = today().isoformat()

    def pay(mode: str, method: str = "BANK") -> dict:
        """Record a 500.00 payment by one mode."""
        body = {
            "party_id": vendor["id"], "settlement_date": t, "amount": "500.00", "method": method,
            "payment_mode": mode, "allocations": [],
        }
        if mode == "CHEQUE":
            body.update({"instrument_reference": "000123", "instrument_date": t})
        return must(a.post("/api/v1/payments", body), "payment")

    chq, cash, xfer = pay("CHEQUE"), pay("CASH", "CASH"), pay("BANK_TRANSFER")
    status, raw = a.raw(f"/api/v1/payments/{chq['id']}/cheque?payee=Override%20Name")
    c.eq((status, raw[:4]), (200, b"%PDF"), "Print cheque with a payee override gives a PDF")
    for what, p in (("cash", cash), ("bank-transfer", xfer)):
        status, raw = a.raw(f"/api/v1/payments/{p['id']}/cheque")
        c.ok(status in (409, 422), f"a {what} payment has no cheque to print", (status, raw[:120]))
    must(a.post(f"/api/v1/payments/{chq['id']}/reverse", {"reason": "check"}), "reverse")
    status, raw = a.raw(f"/api/v1/payments/{chq['id']}/cheque")
    c.ok(status in (409, 422), "a reversed payment prints no cheque", (status, raw[:120]))
finally:
    a.put(f"/api/v1/payments/cheque-layouts/{bank['id']}", {"offset_x_mm": "0", "offset_y_mm": "0", "print_ac_payee": True})
    a.delete(path)
    a.delete(f"/api/v1/finance/bank-details/{petty['id']}")
c.done()
