"""TC-FIN-018: cash flow statement: sections from account groups, opening and closing cash, reconciliation, permission."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _fin import *

c = Check("tc_fin_018")
a = admin()
per = period_of(a)
# make this month hold a sale, a receipt and a purchase
sc = Scene(a)
cust = sc.customer()
with counter(a):
    bill = sc.bill(cust, "4")  # 472.00
receipt(a, cust, "200.00", [(bill, "200.00")])
buy.Scene(a).received_and_billed("5")
CF = f"{FIN}/cash-flow?from_period_id={per['id']}&to_period_id={per['id']}"
cf = must(a.get(CF), "cash flow")
pl = must(a.get(f"{FIN}/profit-loss?accounting_period_id={per['id']}"), "pl")
t = tb(a, per)


def total(lines: list[dict]) -> Decimal:
    """Add a section's amounts."""
    return sum((D(x["amount"]) for x in lines), Decimal(0))


codes = {sec: {x["account_code"] for x in cf[sec]} for sec in ("operating", "investing", "financing")}
c.ok({"1100", "2100"} <= codes["operating"], "receivables and payables (current) are operating", sorted(codes["operating"]))
c.ok("3000" in codes["financing"], "equity (Opening Balance Equity) is financing", sorted(codes["financing"]))
c.ok(not ({"1000", "1005", "1010"} & set().union(*codes.values())), "cash and bank accounts are in no section: they are the cash")
c.eq(D(cf["operating_total"]), D(cf["net_profit"]) + total(cf["operating"]), "operating total = net profit + the operating lines")
c.eq(D(cf["investing_total"]), total(cf["investing"]), "investing total = its lines")
c.eq(D(cf["financing_total"]), total(cf["financing"]), "financing total = its lines")
c.eq(D(cf["net_change"]), D(cf["operating_total"]) + D(cf["investing_total"]) + D(cf["financing_total"]), "net change = the three sections")
c.eq(D(cf["opening_cash"]) + D(cf["net_change"]), D(cf["closing_cash"]), "opening cash + net change = closing cash")
c.eq(cf["is_reconciled"], True, "the statement says it reconciles")
c.eq(D(cf["net_profit"]), D(pl["net_profit"]), "its net profit is the P&L's for the same period")
cash_now = sum((closing(t, k) for k in ("1000", "1005", "1010")), Decimal(0))
c.eq(D(cf["closing_cash"]), cash_now, "closing cash = Cash + Petty Cash + Bank on the trial balance")
c.eq((cf["from_date"], cf["to_date"]), (per["starts_on"], per["ends_on"]), "dates are the period's")
# a run of periods
later = [p for p in all_rows(a, f"{FIN}/accounting-periods") if per["starts_on"] <= p["starts_on"]]
last = sorted(later, key=lambda p: p["starts_on"])[1]
two = must(a.get(f"{FIN}/cash-flow?from_period_id={per['id']}&to_period_id={last['id']}"), "two months")
c.eq(two["is_reconciled"], True, "two months reconcile too")
c.eq(D(two["opening_cash"]), D(cf["opening_cash"]), "a run keeps the first month's opening cash")
# permission: PROFIT_LOSS_VIEW
c.eq(admin("cashier").get(CF)[0], 403, "a Cashier (no PROFIT_LOSS_VIEW) is refused")
c.eq(admin("accountant").get(CF)[0], 200, "an Accountant reads it")
c.eq(a.get(f"{FIN}/cash-flow?from_period_id={last['id']}&to_period_id={per['id']}")[0], 422, "a range running backwards is refused")
c.done()
