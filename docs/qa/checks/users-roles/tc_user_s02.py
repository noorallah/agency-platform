"""03-S02 Roles screen (server half)."""
from _ur import *

c = Check("tc_user_s02"); sc = Scene()
try:
    a = sc.admin
    c.eq(a.get(R)[0], 200, "opens for ROLE_VIEW")
    c.eq(api("seller").get(R)[0], 403, "refused without ROLE_VIEW")
    role = sc.role(a)
    c.eq([r["id"] for r in data(a.get(f"{R}?search={role['code']}")[1])], [role["id"]], "search narrows")
    c.eq(a.get(f"{R}?page_size=101")[0], 422, "page_size cap")
    c.eq(a.get(f"{R}?sort_by=nope")[0], 422, "unlisted sort column")
    c.eq(a.call("PATCH", f"{R}/{role['id']}", {"name": "Renamed"})[0], 200, "edit a custom role")
    c.eq(data(a.get(f"{R}/{role['id']}")[1])["name"], "Renamed", "stored")
    seeded = next(r for r in all_rows(a, R) if r["code"] == "CASHIER")
    c.ok(a.call("PATCH", f"{R}/{seeded['id']}", {"name": "x"})[0] in (403, 422), "a system role cannot be edited")
    c.ok(a.delete(f"{R}/{seeded['id']}")[0] in (403, 422), "a system role cannot be deleted")
    c.eq(data(a.get(f"{R}/{seeded['id']}")[1])["name"], seeded["name"], "the system role is unchanged")
    dup = a.post(R, {"code": role["code"], "name": "Again"})
    c.ok(dup[0] in (409, 422), "a duplicate code is refused", (dup[0], message(dup[1])))
    c.eq(a.post(R, {"code": "ab"})[0], 422, "a required field empty is named")
finally:
    sc.cleanup()
c.done()
