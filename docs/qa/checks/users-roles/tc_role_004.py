"""TC-ROLE-004: a firm admin holds AUDIT_LOG_VIEW and cannot grant it."""
from _ur import *

c = Check("tc_role_004"); sc = Scene()
try:
    a = sc.admin
    c.eq(a.get("/api/v1/audit-logs?page_size=1")[0], 200, "the audit trail opens for a firm admin")
    c.ok("AUDIT_LOG_VIEW" not in [r["code"] for r in all_rows(a, "/api/v1/permissions?search=AUDIT_LOG_VIEW")], "AUDIT_LOG_VIEW is not offered")
    pid = next(r["id"] for r in all_rows(sc.platform, "/api/v1/permissions?search=AUDIT_LOG_VIEW") if r["code"] == "AUDIT_LOG_VIEW")
    role = sc.role(a)
    r = a.put(f"{R}/{role['id']}/permissions", {"ids": [pid]})
    c.ok(r[0] in (403, 422), "granting it is refused", (r[0], message(r[1])))
    c.eq(data(sc.platform.get(f"{R}/{role['id']}/permissions")[1])["ids"], [], "the role holds nothing")
finally:
    sc.cleanup()
c.done()
