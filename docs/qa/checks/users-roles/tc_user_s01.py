"""03-S01 Users screen (server half): offered by USER_VIEW, lists, search, sort and paging behave."""
from _ur import *

c = Check("tc_user_s01"); sc = Scene()
try:
    a = sc.admin
    mine = sc.user("screen")
    c.eq(a.get(U)[0], 200, "a firm admin opens the list")
    c.eq(api("seller").get(U)[0], 403, "a role without USER_VIEW is refused")
    found = data(a.get(f"{U}?search=screen.{sc.tag.lower()}")[1])
    c.eq([r["email"] for r in found], [mine["email"]], "search narrows the list")
    asc = [r["email"].lower() for r in data(a.get(f"{U}?sort_by=email&sort_direction=asc&page_size=50")[1])]
    c.ok(asc == sorted(asc), "email sort ascending is ordered", asc[:5])
    c.eq(a.get(f"{U}?sort_by=password")[0], 422, "an unlisted sort column is refused")
    c.eq(a.get(f"{U}?page_size=101")[0], 422, "page_size over the cap is a 422")
    c.eq(a.call("PATCH", f"{U}/{mine['id']}", {"is_active": False})[0], 200, "deactivate")
    c.eq(len(data(a.get(f"{U}?inactive_only=true&search=screen.{sc.tag.lower()}")[1])), 1, "inactive_only finds them")
    c.eq(len(data(a.get(f"{U}?active_only=true&search=screen.{sc.tag.lower()}")[1])), 0, "active_only does not")
    c.eq(a.delete(f"{U}/{mine['id']}")[0], 204, "delete")
    sc.users.clear()
    c.eq(len(data(a.get(f"{U}?search=screen.{sc.tag.lower()}&deleted_only=true")[1])), 0, "a firm admin cannot list deleted users")
    c.eq(a.post(f"{U}/{mine['id']}/restore")[0], 403, "restore is platform-only")
    gone = data(sc.platform.get(f"{U}?deleted_only=true&search=screen.{sc.tag.lower()}")[1])
    c.eq(len(gone), 1, "a platform admin finds the deleted user")
    c.eq(sc.platform.post(f"{U}/{mine['id']}/restore")[0], 200, "and restores them")
    sc.users.append(mine["id"])
finally:
    sc.cleanup()
c.done()
