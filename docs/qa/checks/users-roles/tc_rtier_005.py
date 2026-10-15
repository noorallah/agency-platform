"""TC-RTIER-005: a platform administrator New writes the global tier only."""
from _ur import *

c = Check("tc_rtier_005"); sc = Scene()
try:
    p = sc.platform
    g1 = sc.user("global1", (one(), two()))
    set_global_roles(sc, g1["id"], ["CUSTOMER_SUPPORT"])
    c.eq(roles_of(p, g1["id"], one()), [], "TEST01 section empty")
    c.eq(roles_of(p, g1["id"], two()), [], "TEST02 section empty")
    c.eq(codes(sc, global_roles_of(p, g1["id"])), ["CUSTOMER_SUPPORT"], "CUSTOMER_SUPPORT is under Applies in every firm")
    g2 = sc.user("global2", (one(),))
    c.eq(p.post(f"{U}/{g2['id']}/apply-template", {"template_id": sc.template("read-only")["id"]})[0], 200, "apply Read Only")
    c.eq(codes(sc, global_roles_of(p, g2["id"])), ["VIEWER"], "VIEWER lands in the global tier")
    c.eq(roles_of(p, g2["id"], one()), [], "and no firm section holds it")
finally:
    sc.cleanup()
c.done()
