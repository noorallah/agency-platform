"""TC-RTIER-008: the server holds a firm administrator to their firm, and a role to a membership."""
from _ur import *

c = Check("tc_rtier_008"); sc = Scene()
try:
    a, p = sc.admin, sc.platform
    sh = shared(sc)
    t2 = sc.user("t2only", (two(),))
    cashier = {"ids": [sc.role_id("CASHIER")]}
    c.refused(a.put(f"{U}/{sh['id']}/firms/{two()}/roles", cashier), 422, "You can only set roles in firms you administer", "write TEST02")
    c.refused(a.get(f"{U}/{sh['id']}/firms/{two()}/roles"), 422, "You can only read roles in firms you administer", "read TEST02")
    c.eq(a.get(f"{U}/{sh['id']}/firms/{one()}/roles")[0], 200, "reading TEST01 is fine")
    c.refused(p.put(f"{U}/{t2['id']}/firms/{one()}/roles", cashier), 422, "Add the user to this firm", "role in a firm they are not in")
    r = a.get(f"{U}/{t2['id']}/firms")
    c.eq((r[0], data(r[1])), (200, []), "a firm admin learns nothing of a TEST02-only user firms")
finally:
    sc.cleanup()
c.done()
