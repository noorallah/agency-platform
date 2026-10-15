"""TC-RTIER-007: a firm administrator form (the reads it is built from)."""
from _ur import *

c = Check("tc_rtier_007"); sc = Scene()
try:
    a = sc.admin
    tt = sc.user("twotier")
    set_global_roles(sc, tt["id"], ["VIEWER", "CUSTOMER_SUPPORT"])
    set_firm_roles(sc, tt["id"], one(), ["ACCOUNTANT", "INVENTORY_MANAGER"])
    c.eq(codes(sc, roles_of(a, tt["id"], one())), ["ACCOUNTANT", "INVENTORY_MANAGER"], "Roles in this firm")
    c.eq(codes(sc, global_roles_of(a, tt["id"])), ["CUSTOMER_SUPPORT", "VIEWER"], "Also applies here")
    mine = data(a.get(f"{U}/{tt['id']}/firms")[1])
    c.eq([m["firm_id"] for m in mine], [one()], "the per-firm editor lists TEST01 only")
finally:
    sc.cleanup()
c.done()
