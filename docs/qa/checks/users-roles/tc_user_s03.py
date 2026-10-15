"""03-S03 Permissions screen (server half): read for PERMISSION_VIEW, writes are not a firm admin."""
from _ur import *

c = Check("tc_user_s03"); sc = Scene()
try:
    a = sc.admin
    c.eq(a.get("/api/v1/permissions")[0], 200, "opens for PERMISSION_VIEW")
    c.eq(api("seller").get("/api/v1/permissions")[0], 403, "refused without it")
    hit = data(a.get("/api/v1/permissions?search=CUSTOMER_VIEW")[1])
    c.ok(any(r["code"] == "CUSTOMER_VIEW" for r in hit), "search finds a code")
    c.eq(a.get("/api/v1/permissions?page_size=101")[0], 422, "page_size cap")
    c.ok(a.post("/api/v1/permissions", {"code": f"QA_{sc.tag}", "name": "x", "module": "qa"})[0] in (403, 422), "a firm admin cannot create a permission")
    one_id = hit[0]["id"]
    c.ok(a.call("PATCH", f"/api/v1/permissions/{one_id}", {"name": "x"})[0] in (403, 422), "nor edit one")
    c.ok(a.delete(f"/api/v1/permissions/{one_id}")[0] in (403, 422), "nor delete one")
    after = data(a.get(f"/api/v1/permissions/{one_id}")[1])
    c.eq(after["code"], hit[0]["code"], "the permission is unchanged")
finally:
    sc.cleanup()
c.done()
