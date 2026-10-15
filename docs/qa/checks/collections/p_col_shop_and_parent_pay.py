"""Probe (b): a shop pays its own bill while the parent pays another shop's; every view agrees; both reverse."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _col import *

c = Check("p_col_shop_and_parent_pay")
a = admin()
sc = Scene(a)
parent = sc.customer()
s1, s2 = (sc.customer(parent_customer_id=parent["id"]) for _ in range(2))
with counter(a):
    b1, b2 = sc.bill(s1, "1"), sc.bill(s2, "2")  # 118.00 and 236.00
day = today().isoformat()


def family() -> dict:
    """Return the parent's family totals."""
    return must(a.get(f"{CU}/{parent['id']}/family"), "family")


def everything() -> dict:
    """Read every view of the three accounts that must agree."""
    out: dict[str, Any] = {}
    for name, who in (("p", parent), ("s1", s1), ("s2", s2)):
        owed, adv = position(a, who)
        acct = must(a.get(f"{CU}/{who['id']}/account"), "account")
        out[name] = {
            "outstanding": owed, "advance": adv,
            "closing": closing(a, who), "account_closing": D(acct["closing_balance"]),
            "account_advance": D(acct["unapplied_advance"]),
        }
    out["b1"] = owing(a, s1, b1)
    out["b2"] = owing(a, s2, b2)
    return out


start = everything()
c.eq((start["s1"]["outstanding"], start["s2"]["outstanding"]), (D("118.00"), D("236.00")), "set-up: the shops owe 118.00 and 236.00")
c.eq(D(family()["total_outstanding"]), D("354.00"), "the family total agrees: 354.00")
# s1 pays its own bill; the parent pays s2's bill with 300.00 (236.00 against the bill, 64.00 on account)
own = data(receipt(a, s1, "118.00", [(b1, "118.00")])[1])
par = data(receipt(a, parent, "300.00", [(b2, "236.00")])[1])
now = everything()
c.eq(now["b1"], D("0"), "the first shop's bill is paid by the shop")
c.eq(now["b2"], D("0"), "the second shop's bill is paid by the parent")
for who in ("s1", "s2"):
    v = now[who]
    c.eq((v["outstanding"], v["closing"], v["account_closing"]), (D("0"), D("0"), D("0")), f"{who}: balance, statement and account all read 0.00")
c.eq((now["p"]["advance"], now["p"]["account_advance"]), (D("64.00"), D("64.00")), "the parent holds the 64.00 left, in both views")
fam = family()
c.eq((D(fam["total_outstanding"]), D(fam["total_unapplied_advance"])), (D("0"), D("64.00")), "the family totals: owes 0.00, holds 64.00")
c.eq(sum(D(m["current_outstanding"]) for m in fam["members"]), D(fam["total_outstanding"]), "the family total is the sum of its members")
for number, who, amount in ((own["settlement_number"], s1, "118.00"), (par["settlement_number"], s2, "236.00")):
    lines = [x for x in must(a.get(f"{CU}/{who['id']}/statement?from_date={day}&to_date={day}"), "statement")["lines"] if x["reference_number"] == number]
    c.eq([D(x["credit"]) for x in lines], [D(amount)], f"{who['code']}'s statement carries {number} for {amount}")
# reverse both
c.eq(a.post(f"{RC}/{own['id']}/reverse", {"reason": "check"})[0], 200, "the shop's receipt is reversed")
c.eq(a.post(f"{RC}/{par['id']}/reverse", {"reason": "check"})[0], 200, "the parent's receipt is reversed")
c.eq(everything(), start, "every figure, in every view, is back where it started")
c.done()
