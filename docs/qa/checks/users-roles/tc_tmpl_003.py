"""TC-TMPL-003: hiring into a job in one step (create, then apply)."""
from _ur import *

c = Check("tc_tmpl_003"); sc = Scene()
try:
    a = sc.admin
    job, _ = sc.hire("jobhire", "counter-sales")
    c.eq(codes(sc, roles_of(a, job["id"], one())), ["BILLING_EXECUTIVE", "CASHIER"], "the job roles")
    hand = sc.user("handhire")
    set_firm_roles(sc, hand["id"], one(), ["CUSTOMER_SUPPORT", "VIEWER"], by=a)
    c.eq(codes(sc, roles_of(a, hand["id"], one())), ["CUSTOMER_SUPPORT", "VIEWER"], "hand hire: exactly those two roles")
finally:
    sc.cleanup()
c.done()
