"""TC-FIN-002: the three statements balance and agree (two invoices, two receipts)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _fin import *

c = Check("tc_fin_002")
a = admin()
per = period_of(a)
before_tb = tb(a, per)
sc = Scene(a)
cust = sc.customer()
with counter(a):
    b1 = sc.bill(cust, "3")  # 354.00
    b2 = sc.bill(cust, "2")  # 236.00
c.eq(receipt(a, cust, "354.00", [(b1, "354.00")])[0], 201, "first receipt, 354.00, in full")
c.eq(receipt(a, cust, "100.00", [(b2, "100.00")])[0], 201, "second receipt, 100.00, part")
t = tb(a, per)
pl = must(a.get(f"{FIN}/profit-loss?accounting_period_id={per['id']}"), "pl")
bs = must(a.get(f"{FIN}/balance-sheet?accounting_period_id={per['id']}"), "bs")
need = {"ledger_account_id", "account_code", "account_name", "account_type", "opening_balance", "period_debit", "period_credit", "closing_balance"}
c.ok(need <= set(t["lines"][0]), "TB lines carry code, account, type, opening, debit, credit, closing", sorted(set(t["lines"][0])))
c.ok(any(x["account_code"] == "1100" and x["account_name"] == "Trade Receivables" for x in t["lines"]), "1100 Trade Receivables is among the rows")
c.eq(t["is_balanced"], True, "TB chip Balanced")
c.eq(D(t["total_debit"]), D(t["total_credit"]), "total debit = total credit")
dr, cr = sums(t)
c.eq((dr, cr), (D(t["total_closing_debit"]), D(t["total_closing_credit"])), "closing totals are the sum of the lines")
c.eq(closing(t, "1100") - closing(before_tb, "1100"), D("590.00") - D("454.00"), "Receivables moved by 590.00 billed less 454.00 received = 136.00")
c.ok(pl["income"] and pl["expenses"], "P&L has Income and Expenses sections")
c.eq(D(pl["net_profit"]), D(pl["total_income"]) - D(pl["total_expense"]), "Net profit = income - expense")
c.ok({"year_to_date_net_profit", "net_profit"} <= set(pl), "with This period and Year to date figures")
c.ok(bs["assets"] and bs["liabilities"] and bs["equity"], "Balance Sheet has Assets, Liabilities, Equity")
c.ok("retained_earnings_brought_forward" in bs and "result_for_the_year" in bs, "with Retained earnings brought forward and Result for the year")
c.eq(bs["is_balanced"], True, "Balance sheet chip Balanced")
c.eq(D(bs["total_assets"]), D(bs["total_liabilities"]) + D(bs["total_equity"]), "Total assets = Liabilities and equity")
c.eq(D(bs["result_for_the_year"]), D(pl["year_to_date_net_profit"]), "the sheet's Result for the year = the P&L's year-to-date net")
c.eq(D(t["total_debit"]), D(t["total_credit"]), "TB debit = credit (restated)")
# Same period, three views by id
c.eq((t["accounting_period_id"], pl["accounting_period_id"], bs["accounting_period_id"]), (per["id"],) * 3, "all three report the one period")
c.done()
