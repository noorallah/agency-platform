"""TC-FIN-028: part of a due waived as a discount on the receipt: owner can, cashier cannot, tax stays."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _col import *

c = Check("tc_col_fin_028")
a = admin()
cashier = admin("cashier")
sc = Scene(a)
held = must(a.get(f"{PA}/settings"), "limits")
limits = {
    "approval_threshold": held["approval_threshold"],
    "rounding_limit": held["rounding_limit"],
    "clearance_discount_percent": held.get("clearance_discount_percent"),
}


def set_percent(value: str | None) -> tuple[int, Any]:
    """Set the clearance percentage as the administrator."""
    return a.put(f"{PA}/settings", {**limits, "clearance_discount_percent": value})


def money_fields(bill_id: str) -> dict:
    """Return the bill's tax and total fields, which a discount must not move."""
    got = must(a.get(f"{SI}/{bill_id}"), "bill")
    return {k: v for k, v in got.items() if "tax" in k.lower() or "total" in k.lower() or k == "grand_total"}


try:
    must(set_percent("5"), "percent 5")
    plain = sc.customer()  # no cash-discount terms
    terms = sc.customer(cash_discount_days=10, cash_discount_percent=2)
    with counter(a):
        a1 = sc.bill(plain, "10")  # 1,180.00
        a2 = sc.bill(plain, "10")
        b1 = sc.bill(terms, "10")
    c.eq(D(a1["grand_total"]), D("1180.00"), "set-up: bills of 1,180.00")
    # 1
    c.eq(cashier.put(f"{PA}/settings", {**limits, "clearance_discount_percent": "9"})[0], 403, "step 1: the Cashier cannot change the percentage")
    c.eq(D(must(a.get(f"{PA}/settings"), "read")["clearance_discount_percent"]), D("5"), "...and it is still 5")
    # 2
    c.refused(
        receipt(cashier, plain, "1180.00", [(a1, "1180.00")], discount_amount="50.00"),
        403, "CLEARANCE_DISCOUNT_GIVE", "step 2: the Cashier's 50.00 discount is refused",
    )
    c.eq(owing(a, plain, a1), D("1180.00"), "nothing was recorded: the bill still owes 1,180.00")
    # 3
    c.refused(
        receipt(a, plain, "1180.00", [(a1, "1180.00")], discount_amount="59.01"),
        422, "which is 59.00", "step 3: 59.01 is over the 5% ceiling",
    )
    c.eq(owing(a, plain, a1), D("1180.00"), "nothing was recorded by that refusal either")
    # 4
    before = money_fields(a1["id"])
    st, body = receipt(a, plain, "1180.00", [(a1, "1180.00")], discount_amount="59.00")
    c.eq(st, 201, "step 4: 59.00 is recorded")
    r = data(body)
    c.eq(D(r["cash_amount"]), D("1121.00"), "cash received 1,121.00")
    c.eq(D(r["discount_amount"]), D("59.00"), "discount 59.00")
    c.eq(owing(a, plain, a1), D("0"), "the bill is closed")
    c.eq(money_fields(a1["id"]), before, "the bill's taxable value, tax and total read as before")
    entry = entry_by_id(a, r["journal_entry_id"])
    c.eq(len(entry["lines"]), 3, "the entry has three lines")
    c.ok(balanced(entry), "and balances")
    c.eq(
        entry_net(a, entry),
        {"BANK": D("1121.00"), "DISCOUNT_ALLOWED": D("59.00"), "ACCOUNTS_RECEIVABLE": D("-1180.00")},
        "Cash 1,121.00 Dr, Discount Allowed 59.00 Dr, Receivables 1,180.00 Cr, no tax account",
    )
    # 5
    c.refused(
        receipt(cashier, terms, "1180.00", [(b1, "1180.00")], discount_amount="30.00"),
        403, "6.40 of this discount is a clearance discount", "step 5: 30.00 is refused, 6.40 being clearance",
    )
    st, body = receipt(cashier, terms, "1180.00", [(b1, "1180.00")], discount_amount="23.60")
    c.eq(st, 201, "the terms' own 23.60 is recorded by the Cashier")
    c.eq(owing(a, terms, b1), D("0"), "and the bill is closed")
    c.eq(D(data(body)["cash_amount"]), D("1156.40"), "cash received 1,156.40")
    # 6
    must(set_percent("0"), "percent 0")
    c.refused(
        receipt(a, plain, "1180.00", [(a2, "1180.00")], discount_amount="1.00"),
        422, "up to 0.00%", "step 6: with the percentage at 0, 1.00 is refused",
    )
    must(set_percent(None), "percent blank")
    st, body = receipt(a, plain, "1180.00", [(a2, "1180.00")], discount_amount="300.00")
    c.eq(st, 201, "with the box blank, 300.00 is recorded")
    c.eq(D(data(body)["cash_amount"]), D("880.00"), "cash received 880.00")
    c.eq(owing(a, plain, a2), D("0"), "and the bill is closed")
finally:
    set_percent(limits["clearance_discount_percent"])
c.done()
