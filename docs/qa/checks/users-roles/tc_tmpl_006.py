"""TC-TMPL-006: a firm administrator template writes the firm tier only."""
from _ur import *

c = Check("tc_tmpl_006"); sc = Scene()
try:
    a = sc.admin
    tt = sc.user("twotier")
    set_global_roles(sc, tt["id"], ["VIEWER", "CUSTOMER_SUPPORT"])
    set_firm_roles(sc, tt["id"], one(), ["ACCOUNTANT", "INVENTORY_MANAGER"])
    r = a.post(f"{U}/{tt['id']}/apply-template", {"template_id": sc.template("counter-sales")["id"]})
    c.eq(r[0], 200, "apply Counter Sales as the firm admin")
    c.eq(codes(sc, global_roles_of(sc.platform, tt["id"])), ["CUSTOMER_SUPPORT", "VIEWER"], "the global tier is untouched")
    c.eq(codes(sc, roles_of(sc.platform, tt["id"], one())), ["BILLING_EXECUTIVE", "CASHIER"], "the TEST01 tier is overwritten")
finally:
    sc.cleanup()
c.done()
