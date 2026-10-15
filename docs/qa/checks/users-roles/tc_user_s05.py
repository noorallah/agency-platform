"""03-S05 User-Firm Assignments (server half): the cross-firm reads are a platform administrator's."""
from _ur import *

c = Check("tc_user_s05"); sc = Scene()
try:
    a, p = sc.admin, sc.platform
    sh = shared(sc)
    c.eq(len(data(p.get(f"{U}/{sh['id']}/firms")[1])), 2, "a platform admin sees both memberships")
    c.eq(len(data(a.get(f"{U}/{sh['id']}/firms")[1])), 1, "a firm admin sees one")
    c.eq(p.get(f"{U}?firm_id={two()}&page_size=5")[0], 200, "a platform admin filters the grid by any firm")
    r = a.get(f"{U}?firm_id={two()}&page_size=5")
    c.ok(r[0] in (403, 422), "a firm admin naming another firm is refused", (r[0], message(r[1])))
    c.eq(a.get(f"{U}?firm_id={one()}&page_size=5")[0], 200, "naming their own firm is fine")
finally:
    sc.cleanup()
c.done()
