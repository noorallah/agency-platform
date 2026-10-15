"""TC-TMPL-009: somebody without role codes has no templates to see."""
from _ur import *

c = Check("tc_tmpl_009"); sc = Scene()
try:
    seller = api("seller")
    c.refused(seller.get(T), 403, "permission", "GET /user-templates as a seller")
    c.eq(seller.get(R)[0], 403, "no roles list")
    c.eq(seller.get(U)[0], 403, "no users list")
    c.eq(seller.get("/api/v1/permissions")[0], 403, "no permissions list")
finally:
    sc.cleanup()
c.done()
