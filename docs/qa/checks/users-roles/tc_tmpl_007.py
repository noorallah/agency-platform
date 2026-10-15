"""TC-TMPL-007: a platform administrator template writes the global tier only."""
from _ur import *

c = Check("tc_tmpl_007"); sc = Scene()
try:
    tt = sc.user("twotier")
    set_global_roles(sc, tt["id"], ["VIEWER", "CUSTOMER_SUPPORT"])
    set_firm_roles(sc, tt["id"], one(), ["ACCOUNTANT", "INVENTORY_MANAGER"])
    r = sc.platform.post(f"{U}/{tt['id']}/apply-template", {"template_id": sc.template("warehouse")["id"]})
    c.eq(r[0], 200, "apply Warehouse as the platform admin")
    c.eq(codes(sc, global_roles_of(sc.platform, tt["id"])), ["INVENTORY_MANAGER"], "the global tier becomes exactly the job")
    c.eq(codes(sc, roles_of(sc.platform, tt["id"], one())), ["ACCOUNTANT", "INVENTORY_MANAGER"], "the TEST01 tier is untouched")
finally:
    sc.cleanup()
c.done()
