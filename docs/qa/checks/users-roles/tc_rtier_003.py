"""TC-RTIER-003: each administrator sees the tier they cannot write."""
from _ur import *

c = Check("tc_rtier_003"); sc = Scene()
try:
    p, a = sc.platform, sc.admin
    sh = shared(sc)
    set_global_roles(sc, sh["id"], ["VIEWER"])
    set_firm_roles(sc, sh["id"], one(), ["SALES_MANAGER"])
    set_firm_roles(sc, sh["id"], two(), ["CASHIER"])
    c.eq(codes(sc, global_roles_of(a, sh["id"])), ["VIEWER"], "firm admin sees Also applies here")
    c.eq(codes(sc, roles_of(p, sh["id"], one())), ["SALES_MANAGER"], "platform sees TEST01")
    c.eq(codes(sc, roles_of(p, sh["id"], two())), ["CASHIER"], "platform sees TEST02")
    set_firm_roles(sc, sh["id"], two(), [])
    c.eq(roles_of(p, sh["id"], two()), [], "TEST02 cleared")
    c.eq(codes(sc, roles_of(p, sh["id"], one())), ["SALES_MANAGER"], "TEST01 left alone")
finally:
    sc.cleanup()
c.done()
