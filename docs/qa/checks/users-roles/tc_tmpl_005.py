"""TC-TMPL-005: applying a job replaces what somebody holds."""
from _ur import *

c = Check("tc_tmpl_005"); sc = Scene()
try:
    a = sc.admin
    manual = sc.user("manual")
    set_firm_roles(sc, manual["id"], one(), ["SALES_EXECUTIVE", "CUSTOMER_SUPPORT"], by=a)
    r = a.post(f"{U}/{manual['id']}/apply-template", {"template_id": sc.template("counter-sales")["id"]})
    c.eq(r[0], 200, "apply Counter Sales")
    c.eq(codes(sc, roles_of(a, manual["id"], one())), ["BILLING_EXECUTIVE", "CASHIER"], "roles become exactly the job")
    # an inactive or unknown template is refused
    c.ok(a.post(f"{U}/{manual['id']}/apply-template", {"template_id": BAD_ID})[0] in (404, 422), "an unknown template is refused")
finally:
    sc.cleanup()
c.done()
