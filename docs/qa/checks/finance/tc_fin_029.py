"""TC-FIN-029 (server half): the figures an Excel download is built from. The sheet itself is made by the desktop; what can be driven over HTTP is that every row of a period is reachable, and that totals, running balances and month columns add up exactly."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _fin import *

c = Check("tc_fin_029")
a = admin()
per = period_of(a)
sc = Scene(a)
cust = sc.customer()
with counter(a):
    b1, b2 = sc.bill(cust, "3"), sc.bill(cust, "1")  # 354.00 and 118.00
receipt(a, cust, "100.00", [(b1, "100.00")])
bs = buy.Scene(a)
buy_bill = bs.received_and_billed("2")[2]

# 1: a register is complete however it is paged (the sheet holds every row, not the first page)
REG = f"/api/v1/sales-invoices/reports/register?from_date={per['starts_on']}&to_date={today().isoformat()}"
small = all_rows(a, REG, size=7)
big = all_rows(a, REG, size=50)
total = a.get(f"{REG}&page_size=1")[1]["pagination"]["total_records"]
c.eq((len(small), len(big)), (total, total), "the register reads the same row count whatever the page size, and it is the pagination total")
c.eq(len({r["invoice_id"] for r in small}), len(small), "no invoice is listed twice across pages")
c.eq(sum((D(r["grand_total"]) for r in small), Decimal(0)), sum((D(r["grand_total"]) for r in big), Decimal(0)), "the page sizes add to the same figure")
c.ok(b1["invoice_number"] in {r["invoice_number"] for r in small} and b2["invoice_number"] in {r["invoice_number"] for r in small}, "this run's two bills are in it")
first = next(r for r in small if r["invoice_number"] == b1["invoice_number"])
c.eq(D(first["grand_total"]), D("354.00"), "the first bill's total is 354.00 exactly")

# 5: a statement: opening first, closing last, each running balance follows
day = today().isoformat()
st = must(a.get(f"{CU}/{cust['id']}/statement?from_date={day}&to_date={day}"), "statement")
bal = D(st["opening_balance"])
ok = True
for ln in st["lines"]:
    bal = bal + D(ln["debit"]) - D(ln["credit"])
    ok = ok and bal == D(ln["balance"])
c.eq(ok, True, "every statement line's balance = the one before + debit - credit")
c.eq(bal, D(st["closing_balance"]), "the last balance is the closing balance")
c.eq((D(st["opening_balance"]), D(st["closing_balance"])), (D("0.00"), D("372.00")), "opening 0.00, closing 354.00 + 118.00 - 100.00 = 372.00")
# 6: ageing: bands add up to the outstanding
age = data(a.get(f"/api/v1/customers/ageing?customer_id={cust['id']}")[1])[0]
c.eq(sum((D(b["amount"]) for b in age["buckets"]), Decimal(0)), D(age["total_outstanding"]), "ageing bands add up to the outstanding total")
c.eq(D(age["total_outstanding"]), D("372.00"), "372.00")

# 8: the trial balance's Total line is the sum of its columns
t = tb(a, per)
for col, total_key in (("period_debit", "total_period_debit"), ("period_credit", "total_period_credit"), ("closing_debit", "total_closing_debit"), ("closing_credit", "total_closing_credit"), ("opening_debit", "total_opening_debit"), ("opening_credit", "total_opening_credit")):
    c.eq(sum((D(x[col]) for x in t["lines"]), Decimal(0)), D(t[total_key]), f"trial balance {col} adds to the Total line")

# 9: profit and loss month by month: a column per month, then Total
fy = next(y for y in all_rows(a, f"{FIN}/financial-years") if y["code"] == "FY2026")
months = sorted((p for p in all_rows(a, f"{FIN}/accounting-periods") if p["financial_year_id"] == fy["id"]), key=lambda p: p["starts_on"])
rng = must(a.get(f"{FIN}/profit-loss/range?from_period_id={months[0]['id']}&to_period_id={per['id']}"), "range")
c.eq(len(rng["months"]), 7, "April to October: seven month columns")
for line in rng["income"] + rng["expenses"]:
    c.eq(sum((D(m) for m in line["months"]), Decimal(0)), D(line["amount"]), f"{line['account_code']}: the months add up to the Total column")
c.eq(sum((D(m) for m in rng["monthly_net_profit"]), Decimal(0)), D(rng["net_profit"]), "net profit by month adds up to the Total")
c.eq(D(rng["total_income"]) - D(rng["total_expense"]), D(rng["net_profit"]), "income - expense = net profit")
one = must(a.get(f"{FIN}/profit-loss?accounting_period_id={per['id']}"), "month")
c.eq(D(rng["monthly_net_profit"][-1]), D(one["net_profit"]), "the October column equals the single-month P&L")

# 10: a ledger: opening, each line, closing
cash = account(a, "1000")
gl = must(a.get(f"{FIN}/general-ledger/{cash['id']}?accounting_period_id={per['id']}&page_size=200"), "ledger")
run = D(gl["opening_balance"])
ok = True
for ln in gl["lines"]:
    run = run + D(ln["debit_amount"]) - D(ln["credit_amount"])
    ok = ok and run == D(ln["running_balance"])
c.eq(ok, True, "every ledger line's running balance follows from the one before")
c.eq(run, D(gl["closing_balance"]), "the last running balance is the closing balance")
c.eq((D(gl["opening_balance"]) + D(gl["total_debit"]) - D(gl["total_credit"])), D(gl["closing_balance"]), "opening + debits - credits = closing")
c.eq(closing(t, "1000"), D(gl["closing_balance"]), "and it equals the trial balance's closing for Cash")

# 12: payables by month: row totals and the Total line
pay = must(a.get("/api/v1/purchase-invoices/reports/payables"), "payables")
bad = []
for r in pay["rows"]:
    parts = D(r["older"]) + sum((D(x) for x in r["amounts"]), Decimal(0)) + D(r["later"]) + D(r["credits"])
    if parts != D(r["total"]):
        bad.append((r["vendor_name"], parts, r["total"]))
c.eq(bad, [], "each supplier's row total = older + the month columns + later + credits (credits are carried negative)")
mine = next(r for r in pay["rows"] if r["vendor_id"] == bs.vendor["id"])
c.eq(D(mine["total"]), D("236.00"), "this run's supplier owes 236.00 (2 x 100.00 + 18% GST)")
c.eq(D(mine["amounts"][-1]), D("236.00"), "in this month's column")
c.done()
