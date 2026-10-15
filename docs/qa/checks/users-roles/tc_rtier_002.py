"""TC-RTIER-002: saving the form unchanged keeps every firm own roles (the regression case)."""
from _ur import *

c = Check("tc_rtier_002"); sc = Scene()
try:
    p = sc.platform
    sh = shared(sc)
    set_global_roles(sc, sh["id"], ["VIEWER"])
    set_firm_roles(sc, sh["id"], one(), ["SALES_MANAGER"])
    set_firm_roles(sc, sh["id"], two(), ["CASHIER"])
    # the form saves the profile, then the roles field (the global set) unchanged
    c.eq(p.call("PATCH", f"{U}/{sh['id']}", {"full_name": f"shared {sc.tag}"})[0], 200, "profile save")
    c.eq(p.put(f"{U}/{sh['id']}/roles", {"ids": [sc.role_id("VIEWER")]})[0], 200, "roles save, unchanged")
    c.eq(codes(sc, roles_of(p, sh["id"], one())), ["SALES_MANAGER"], "TEST01 still SALES_MANAGER")
    c.eq(codes(sc, roles_of(p, sh["id"], two())), ["CASHIER"], "TEST02 still CASHIER")
    c.eq(codes(sc, global_roles_of(p, sh["id"])), ["VIEWER"], "VIEWER still global, and only that")
finally:
    sc.cleanup()
c.done()
