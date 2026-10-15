"""TC-RTIER-001: the platform form writes the global set; Roles by firm writes one firm."""
from _ur import *

c = Check("tc_rtier_001"); sc = Scene()
try:
    p = sc.platform
    sh = shared(sc)
    c.eq(global_roles_of(p, sh["id"]), [], "no roles to begin with")
    set_global_roles(sc, sh["id"], ["VIEWER"])
    set_firm_roles(sc, sh["id"], one(), ["SALES_MANAGER"])
    c.eq(codes(sc, global_roles_of(p, sh["id"])), ["VIEWER"], "VIEWER is the global set")
    c.eq(codes(sc, roles_of(p, sh["id"], one())), ["SALES_MANAGER"], "TEST01 holds SALES_MANAGER")
    c.eq(roles_of(p, sh["id"], two()), [], "TEST02 holds nothing yet")
    set_firm_roles(sc, sh["id"], two(), ["CASHIER"])
    c.eq(codes(sc, roles_of(p, sh["id"], two())), ["CASHIER"], "TEST02 saved")
    c.eq(codes(sc, roles_of(p, sh["id"], one())), ["SALES_MANAGER"], "TEST01 still SALES_MANAGER: one save, one firm")
    c.eq(codes(sc, global_roles_of(p, sh["id"])), ["VIEWER"], "the global set is untouched by firm saves")
finally:
    sc.cleanup()
c.done()
