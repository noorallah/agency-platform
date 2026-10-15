"""TC-FIN-037: the discount at collection is the firm administrator's alone: a firm manager is refused."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _col import *

c = Check("tc_col_fin_037")
a = admin()
manager = admin("manager")
sc = Scene(a)
held = must(a.get(f"{PA}/settings"), "limits")
limits = {
    "approval_threshold": held["approval_threshold"],
    "rounding_limit": held["rounding_limit"],
    "clearance_discount_percent": held.get("clearance_discount_percent"),
}
try:
    must(a.put(f"{PA}/settings", {**limits, "clearance_discount_percent": "5"}), "percent 5")
    cust = sc.customer()
    with counter(a):
        bill = sc.bill(cust, "10")  # 1,180.00
    # 1
    st, body = manager.put(f"{PA}/settings", {**limits, "approval_threshold": "2500", "clearance_discount_percent": "5"})
    c.eq(st, 200, "step 1: the manager saves the threshold with the percentage unchanged")
    now = must(a.get(f"{PA}/settings"), "read")
    c.eq(D(now["approval_threshold"]), D("2500"), "the threshold is 2,500")
    c.eq(D(now["clearance_discount_percent"]), D("5"), "the percentage is still 5")
    c.refused(
        manager.put(f"{PA}/settings", {**limits, "approval_threshold": "2500", "clearance_discount_percent": "9"}),
        403, "CLEARANCE_DISCOUNT_GIVE", "the manager cannot change the percentage",
    )
    c.eq(D(must(a.get(f"{PA}/settings"), "read")["clearance_discount_percent"]), D("5"), "which is still 5")
    # 2
    c.refused(
        receipt(manager, cust, "1180.00", [(bill, "1180.00")], discount_amount="50.00"),
        403, "CLEARANCE_DISCOUNT_GIVE", "step 2: the manager's 50.00 discount is refused",
    )
    c.eq(owing(a, cust, bill), D("1180.00"), "nothing recorded; the bill still owes 1,180.00")
    # 3
    st, body = receipt(a, cust, "1180.00", [(bill, "1180.00")], discount_amount="50.00")
    c.eq(st, 201, "step 3: the administrator records it")
    c.eq(D(data(body)["cash_amount"]), D("1130.00"), "cash received 1,130.00")
    c.eq(owing(a, cust, bill), D("0"), "the bill is closed")
    # 4
    st, body = a.put(f"{PA}/settings", {**limits, "approval_threshold": "2500", "clearance_discount_percent": "10"})
    c.eq(st, 200, "step 4: the administrator saves 10")
    c.eq(D(must(a.get(f"{PA}/settings"), "read")["clearance_discount_percent"]), D("10"), "the percentage reads 10")
finally:
    a.put(f"{PA}/settings", limits)
c.done()
