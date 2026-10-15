"""Probe: a firm administrator granting a PLATFORM_* (platform-only) permission code to a role."""
from _ur import *

c = Check("p_ur_platform_code_grant"); sc = Scene()
try:
    a, p = sc.admin, sc.platform
    visible = {r["code"] for r in all_rows(a, "/api/v1/permissions")}
    platform_only = [r for r in all_rows(p, "/api/v1/permissions") if r["code"] not in visible]
    c.ok(len(platform_only) > 0, "there are platform-only codes to try", len(platform_only))
    role = sc.role(a)
    for row in platform_only:
        r = a.put(f"{R}/{role['id']}/permissions", {"ids": [row["id"]]})
        c.ok(r[0] in (403, 422), f"granting {row['code']} is refused", (r[0], message(r[1])))
    held = data(p.get(f"{R}/{role['id']}/permissions")[1])["ids"]
    c.eq(held, [], "the role holds none of them")
    # one allowed code mixed with a platform one: all or nothing
    ok_id = next(r["id"] for r in all_rows(a, "/api/v1/permissions?search=SALES_VIEW") if r["code"] == "SALES_VIEW")
    if platform_only:
        r = a.put(f"{R}/{role['id']}/permissions", {"ids": [ok_id, platform_only[0]["id"]]})
        c.ok(r[0] in (403, 422), "a mixed list is refused as a whole", (r[0], message(r[1])))
        c.eq(data(p.get(f"{R}/{role['id']}/permissions")[1])["ids"], [], "and nothing was half-applied")
    # a system role cannot be edited into holding one either
    cashier = next(r for r in all_rows(a, R) if r["code"] == "CASHIER")
    before = sorted(data(p.get(f"{R}/{cashier['id']}/permissions")[1])["ids"])
    if platform_only:
        r = a.put(f"{R}/{cashier['id']}/permissions", {"ids": before + [platform_only[0]["id"]]})
        c.ok(r[0] in (403, 422), "a system role cannot be given a platform code", (r[0], message(r[1])))
    c.eq(sorted(data(p.get(f"{R}/{cashier['id']}/permissions")[1])["ids"]), before, "CASHIER is unchanged")
finally:
    sc.cleanup()
c.done()
