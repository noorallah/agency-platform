"""TC-RTIER-006: the firm switcher has no say in where a role lands."""
from _ur import *

c = Check("tc_rtier_006"); sc = Scene()
try:
    p = sc.platform
    sh = shared(sc)
    set_global_roles(sc, sh["id"], ["VIEWER"])
    set_firm_roles(sc, sh["id"], one(), ["SALES_MANAGER"])
    set_firm_roles(sc, sh["id"], two(), ["CASHIER"])
    inside = p.inside(one())
    r = inside.put(f"{U}/{sh['id']}/roles", {"ids": [sc.role_id("VIEWER"), sc.role_id("CUSTOMER_SUPPORT")]})
    c.eq(r[0], 200, "save the roles field while switched into TEST01")
    c.eq(codes(sc, global_roles_of(p, sh["id"])), ["CUSTOMER_SUPPORT", "VIEWER"], "CUSTOMER_SUPPORT is global")
    c.eq(codes(sc, roles_of(p, sh["id"], one())), ["SALES_MANAGER"], "TEST01 section unchanged")
    c.eq(codes(sc, roles_of(p, sh["id"], two())), ["CASHIER"], "TEST02 section unchanged")
finally:
    sc.cleanup()
c.done()
