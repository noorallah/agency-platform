"""Probe: a role code spelling a reserved code in another case, or with padding."""
from _ur import *

c = Check("p_ur_reserved_case"); sc = Scene()
try:
    before = {r["code"] for r in all_rows(sc.platform, R)}
    for who, a in (("firm admin", sc.admin), ("platform admin", sc.platform)):
        for code in ("Platform_Admin", "PLATFORM_ADMIN", "platform_Admin", " platform_admin", "platform_admin ",
                     "platform_admin\n", "platform_admin​", "license_admin", "support_admin", "system_auditor", "firm_manager"):
            r = a.post(R, {"code": code, "name": "Bad"})
            c.ok(r[0] == 422, f"{who}: role code {code!r} is refused", (r[0], message(r[1])))
            if r[0] == 201:
                sc.roles.append((a, data(r[1])["id"]))
    after = {r["code"] for r in all_rows(sc.platform, R)}
    c.eq(sorted(after - before), [], "no new role row exists")
    # the reserved word inside a longer code is an ordinary code
    ok = sc.role(sc.admin, code=f"qa-platform_admin-{sc.tag.lower()}")
    c.eq(ok["is_system"], False, "a longer code that merely contains it is allowed")
finally:
    sc.cleanup()
c.done()
