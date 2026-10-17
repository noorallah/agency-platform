"""Probe: after a sale and a purchase the trial balance balances, P&L profit equals the balance sheet's result for the year, and every figure is the exact decimal."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _fin import *

c = Check("p_fin_tb_pl")
a = admin()
per = period_of(a)


def snapshot() -> dict:
    """Read the three statements and the cash flow for this period."""
    return {
        "tb": tb(a, per),
        "pl": must(a.get(f"{FIN}/profit-loss?accounting_period_id={per['id']}"), "pl"),
        "bs": must(a.get(f"{FIN}/balance-sheet?accounting_period_id={per['id']}"), "bs"),
        "cf": must(a.get(f"{FIN}/cash-flow?from_period_id={per['id']}&to_period_id={per['id']}"), "cf"),
    }


def agree(s: dict, when: str) -> None:
    """The relationships the three statements must keep, to the paisa."""
    t, pl, bs, cf = s["tb"], s["pl"], s["bs"], s["cf"]
    dr, cr = sums(t)
    c.eq(dr, cr, f"{when}: the lines' closing debits equal their closing credits")
    c.eq(D(t["total_closing_debit"]), D(t["total_closing_credit"]), f"{when}: the trial balance's own totals agree")
    c.eq(D(t["total_closing_debit"]), dr, f"{when}: the printed total is the sum of the lines")
    c.eq(t["is_balanced"], True, f"{when}: the trial balance says Balanced")
    c.eq(D(pl["total_income"]) - D(pl["total_expense"]), D(pl["net_profit"]), f"{when}: P&L net = income - expense")
    c.eq(D(pl["year_to_date_income"]) - D(pl["year_to_date_expense"]), D(pl["year_to_date_net_profit"]), f"{when}: year-to-date net = income - expense")
    c.eq(D(bs["result_for_the_year"]), D(pl["year_to_date_net_profit"]), f"{when}: the sheet's Result for the year equals the P&L year to date")
    c.eq(D(bs["total_assets"]), D(bs["total_liabilities"]) + D(bs["total_equity"]), f"{when}: assets = liabilities + equity")
    c.eq(sum((D(x["amount"]) for x in bs["assets"]), Decimal(0)), D(bs["total_assets"]), f"{when}: asset lines add to the total")
    c.eq(bs["is_balanced"], True, f"{when}: the balance sheet says Balanced")
    c.eq(cf["is_reconciled"], True, f"{when}: the cash flow reconciles")
    c.eq(D(cf["opening_cash"]) + D(cf["net_change"]), D(cf["closing_cash"]), f"{when}: opening cash + movement = closing cash")


before = snapshot()
agree(before, "before")

# a sale of 10 at 100.00 (cost 60.00) and a purchase of 10 at 100.00, both 18% GST
sc = Scene(a)
cust = sc.customer()
with counter(a):
    sale = sc.bill(cust, "10")
c.eq(D(sale["grand_total"]), D("1180.00"), "the sale is 1,180.00")
_, _, bill = buy.Scene(a).received_and_billed("10")
c.eq(D(bill["grand_total"]), D("1180.00"), "the purchase is 1,180.00")
after = snapshot()
agree(after, "after")


def delta(code: str) -> Decimal:
    """Movement of an account's closing (debit positive) over the two trades."""
    return closing(after["tb"], code) - closing(before["tb"], code)


c.eq(delta("1100"), D("1180.00"), "Receivables up by the sale's 1,180.00")
c.eq(delta("4000"), D("-1000.00"), "Sales credited 1,000.00")
c.eq(delta("2220") + delta("2230"), D("-180.00"), "output CGST+SGST credited 180.00")
c.eq(delta("5200"), D("600.00"), "Cost of goods sold debited 600.00 (10 x 60.00 cost)")
c.eq(delta("2100"), D("-1180.00"), "Payables credited the purchase's 1,180.00")
c.eq(delta("1320") + delta("1330"), D("180.00"), "input CGST+SGST debited 180.00")
c.eq(delta("1200"), D("30000.00") + D("1000.00") - D("600.00"), "Inventory: +30,000.00 opening stock of the scene (500 x 60.00), +1,000.00 bought, -600.00 sold at cost")
c.eq(delta("3000"), D("-30000.00"), "Opening Balance Equity credited with that opening stock")
pl_d = lambda k: D(after["pl"][k]) - D(before["pl"][k])  # noqa: E731
c.eq(pl_d("total_income"), D("1000.00"), "P&L income up exactly 1,000.00")
c.eq(delta("5700"), D("23.60"), "Loyalty Expense debited 23.60 (2 percent of 1,180.00, earned with the sale)")
c.eq(delta("2600"), D("-23.60"), "Loyalty Payable credited 23.60")
c.eq(pl_d("total_expense"), D("623.60"), "P&L expense up exactly 623.60 (600.00 cost + 23.60 loyalty; the purchase is stock, not an expense)")
c.eq(pl_d("net_profit"), D("376.40"), "profit up exactly 376.40")
c.eq(D(after["bs"]["result_for_the_year"]) - D(before["bs"]["result_for_the_year"]), D("376.40"), "balance sheet result for the year up 376.40")
c.done()
