"""TC-ROLE-003: no role may be named platform_admin."""
from _ur import *

c = Check("tc_role_003"); sc = Scene()
try:
    a = sc.admin
    for code in ("platform_admin", "firm_admin", "cashier", "system_auditor", "support_admin", "license_admin"):
        r = a.post(R, {"code": code, "name": "Bad"})
        c.refused(r, 422, "reserved", f"role code {code}")
        if r[0] == 201:
            sc.roles.append((a, data(r[1])["id"]))
    for code in ("FIRM_ADMIN", "Cashier", "PLATFORM_ADMIN"):
        r = a.post(R, {"code": code, "name": "Bad"})
        c.eq(r[0], 422, f"{code} is refused earlier, by the code pattern")
        if r[0] == 201:
            sc.roles.append((a, data(r[1])["id"]))
    # the same through the platform admin: a reserved code is reserved for everybody
    r = sc.platform.post(R, {"code": "platform_admin", "name": "Bad"})
    c.refused(r, 422, "reserved", "platform admin writing platform_admin")
    if r[0] == 201:
        sc.roles.append((sc.platform, data(r[1])["id"]))
    names = [x["code"] for x in all_rows(sc.platform, f"{R}?search=platform_admin")]
    c.eq(names.count("platform_admin"), 0, "no lower-case row exists")
finally:
    sc.cleanup()
c.done()
