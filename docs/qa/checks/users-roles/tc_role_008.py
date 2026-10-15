"""TC-ROLE-008: editing a role signs out everyone holding it."""
from _ur import *
from _roles import night_desk, NIGHT_DESK

c = Check("tc_role_008"); sc = Scene()
try:
    role = night_desk(sc)
    holder = sc.user("holder")
    must(sc.admin.put(f"{U}/{holder['id']}/firms/{one()}/roles", {"ids": [role["id"]]}), "give the role")
    u = sc.sign_in(holder)
    c.eq(u.post("/api/v1/receipts", {})[0], 422, "Record Receipt is there")
    keep = []
    for want in NIGHT_DESK:
        if want != "RECEIPT_CREATE":
            keep.append(next(r["id"] for r in all_rows(sc.admin, f"/api/v1/permissions?search={want}") if r["code"] == want))
    c.eq(sc.admin.put(f"{R}/{role['id']}/permissions", {"ids": keep})[0], 200, "untick RECEIPT_CREATE")
    c.eq(u.get("/api/v1/customers")[0], 401, "signed out on the next click")
    u2 = sc.sign_in(holder)
    c.eq(u2.get("/api/v1/customers")[0], 200, "the menu is unchanged (customers still open)")
    c.eq(u2.get("/api/v1/receipts?page_size=1")[0], 200, "Receipts still opens")
    c.eq(u2.post("/api/v1/receipts", {})[0], 403, "Record Receipt is gone")
finally:
    sc.cleanup()
c.done()
