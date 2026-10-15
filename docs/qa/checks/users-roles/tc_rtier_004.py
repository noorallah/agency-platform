"""TC-RTIER-004: a firm admin Roles by firm is their firm only, and cannot clear a global grant."""
from _ur import *

c = Check("tc_rtier_004"); sc = Scene()
try:
    p, a = sc.platform, sc.admin
    sh = shared(sc)
    set_global_roles(sc, sh["id"], ["VIEWER"])
    set_firm_roles(sc, sh["id"], one(), ["SALES_MANAGER"])
    set_firm_roles(sc, sh["id"], two(), ["CASHIER"])
    c.refused(a.put(f"{U}/{sh['id']}/firms/{two()}/roles", {"ids": []}), 422, "You can only set roles in firms you administer", "write TEST02")
    c.refused(a.get(f"{U}/{sh['id']}/firms/{two()}/roles"), 422, "You can only read roles in firms you administer", "read TEST02")
    c.eq(a.put(f"{U}/{sh['id']}/firms/{one()}/roles", {"ids": []})[0], 200, "remove SALES_MANAGER in TEST01")
    c.eq(roles_of(p, sh["id"], one()), [], "removed in TEST01")
    c.eq(codes(sc, global_roles_of(p, sh["id"])), ["VIEWER"], "VIEWER survives")
    c.eq(codes(sc, roles_of(p, sh["id"], two())), ["CASHIER"], "TEST02 is untouched")
finally:
    sc.cleanup()
c.done()
