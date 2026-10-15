"""TC-FIN-026: ready-made accounts Capital, Drawings, Petty Cash, Transport, Fuel (once each, in both firms), a contra voucher between cash accounts."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _fin import *

c = Check("tc_fin_026")
a = admin()
b = admin("admin2")
WANT = {
    "1005": ("Petty Cash", "ASSET", None),
    "3100": ("Drawings", "EQUITY", None),
    "3200": ("Capital", "EQUITY", None),
    "6450": ("Transport", "EXPENSE", "IEXP"),
    "6460": ("Fuel", "EXPENSE", "IEXP"),
}
for who, api in (("firm one", a), ("firm two", b)):
    groups = {g["id"]: g["code"] for g in rows_of(api.get(f"{FIN}/account-groups?page_size=100"))}
    rows = rows_of(api.get(f"{FIN}/ledger-accounts?page_size=200"))
    for code, (name, kind, group) in WANT.items():
        found = [r for r in rows if r["code"] == code or r["name"] == name]
        c.eq(len(found), 1, f"{who}: {name} is there once")
        if len(found) == 1:
            r = found[0]
            c.eq((r["code"], r["name"], r["account_type"]), (code, name, kind), f"{who}: {name} is {code}, {kind}")
            if group:
                c.eq(groups.get(r["account_group_id"]), group, f"{who}: {name} sits in {group}")

ex = data(a.get("/api/v1/expenses/accounts")[1])
offered = {x["code"] for x in ex["expense_accounts"]}
paid_from = {x["code"] for x in ex["paid_from_accounts"]}
c.ok({"6450", "6460"} <= offered, "Transport and Fuel are offered as an expense", sorted(offered))
c.ok("1005" in paid_from, "Petty Cash is offered under Paid from", sorted(paid_from))
money = {x["code"]: x["kind"] for x in rows_of(a.get("/api/v1/contra-vouchers/money-accounts"))}
c.eq(money.get("1005"), "CASH", "Petty Cash is a cash account in the contra voucher")


def book_total() -> Decimal:
    """Closing balance of the cash book (the last row's running balance)."""
    rows = all_rows(a, f"{FIN}/reports/cash-book")
    return D(rows[-1]["balance"]) if rows else Decimal(0)


before = book_total()
st, made = a.post("/api/v1/contra-vouchers", {"voucher_date": today().isoformat(), "from_account_id": account(a, "1000")["id"], "to_account_id": account(a, "1005")["id"], "amount": "50.00"})
c.eq(st, 201, "the contra voucher posts")
v = data(made)
c.eq((v["kind"], v["status"]), ("CASH_TRANSFER", "POSTED"), "cash to cash, posted")
c.eq(book_total(), before, "the cash book's total is unchanged (both sides are cash)")
e = entry_by_id(a, v["journal_entry_id"])
c.ok(balanced(e), "its journal balances")
c.eq(sorted((D(l["debit_amount"]), D(l["credit_amount"])) for l in e["lines"]), [(D("0"), D("50.00")), (D("50.00"), D("0"))], "Dr 50.00 / Cr 50.00")
c.refused(a.post("/api/v1/contra-vouchers", {"voucher_date": today().isoformat(), "from_account_id": account(a, "1000")["id"], "to_account_id": account(a, "1000")["id"], "amount": "5.00"}), 422, "", "a transfer from an account to itself is refused")
c.eq(admin("viewer").post("/api/v1/contra-vouchers", {"voucher_date": today().isoformat(), "from_account_id": account(a, "1000")["id"], "to_account_id": account(a, "1005")["id"], "amount": "1.00"})[0], 403, "a Viewer cannot post a contra voucher")
c.done()
