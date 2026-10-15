"""TC-ROLE-002: creating a custom role; the platform codes are never offered."""
from _ur import *

c = Check("tc_role_002"); sc = Scene()
try:
    a = sc.admin
    for code in ("FIRM_CREATE", "PLATFORM_SETTINGS", "VOID_INVOICE", "AUDIT_LOG_VIEW"):
        found = [r["code"] for r in all_rows(a, f"/api/v1/permissions?search={code}")]
        c.ok(code not in found, f"{code} is not offered to a firm admin", found)
    mine = a.get("/api/v1/permissions?page_size=1")
    theirs = sc.platform.get("/api/v1/permissions?page_size=1")
    n_firm, n_all = mine[1]["pagination"]["total_records"], theirs[1]["pagination"]["total_records"]
    c.ok(0 < n_firm < n_all, "platform codes are filtered out of a firm admin read", (n_firm, n_all))
    role = sc.role(a)
    c.eq((role["is_system"], role["firm_id"]), (False, one()), "a custom role of this firm")
    perms = {}
    for code in ("SALES_VIEW", "CUSTOMER_VIEW"):
        perms[code] = next(r["id"] for r in all_rows(a, f"/api/v1/permissions?search={code}") if r["code"] == code)
    c.eq(a.put(f"{R}/{role['id']}/permissions", {"ids": list(perms.values())})[0], 200, "permissions saved")
    got = data(a.get(f"{R}/{role['id']}/permissions")[1])
    c.eq(len(got["ids"]), 2, "the role holds the two codes")
finally:
    sc.cleanup()
c.done()
