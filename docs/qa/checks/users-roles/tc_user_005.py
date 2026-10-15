"""TC-USER-005: a platform administrator's New form offers every firm."""
from _ur import *

c = Check("tc_user_005"); sc = Scene()
try:
    p = sc.platform
    listed = [r["code"] for r in all_rows(p, "/api/v1/firms")]
    c.ok("TEST01" in listed and "TEST02" in listed, "/firms lists every firm", listed)
    mine = data(p.get("/api/v1/me/firms")[1])
    c.ok(any(r["id"] == one() for r in mine) and any(r["id"] == two() for r in mine),
         "me/firms for ALL_FIRMS offers every active firm")
    me = data(p.get("/api/v1/me")[1])
    c.eq(me["is_platform_admin"], True, "the account is a platform administrator")
    c.eq(me["primary_firm_id"], None, "who belongs to no firm of their own")
finally:
    sc.cleanup()
c.done()
