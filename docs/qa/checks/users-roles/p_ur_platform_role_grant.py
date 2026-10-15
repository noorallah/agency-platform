"""Probe: a firm administrator granting a platform role (or itself anything) to a person."""
from _ur import *

c = Check("p_ur_platform_role_grant"); sc = Scene()
try:
    a, p = sc.admin, sc.platform
    victim = sc.user("victim")
    plat = {r["code"]: r["id"] for r in all_rows(p, R) if r["code"] in ("PLATFORM_ADMIN", "LICENSE_ADMIN", "SYSTEM_AUDITOR")}
    c.eq(sorted(plat), ["LICENSE_ADMIN", "PLATFORM_ADMIN", "SYSTEM_AUDITOR"], "the platform roles exist")
    for code, rid in plat.items():
        r = a.put(f"{U}/{victim['id']}/firms/{one()}/roles", {"ids": [rid]})
        c.ok(r[0] in (403, 422), f"firm tier: granting {code} is refused", (r[0], message(r[1])))
        r = a.put(f"{U}/{victim['id']}/roles", {"ids": [rid]})
        c.ok(r[0] in (403, 422), f"global tier: granting {code} is refused", (r[0], message(r[1])))
        r = a.post(T, {"code": f"qa-pl-{code.lower()}-{sc.tag.lower()}", "name": "x", "role_ids": [rid]})
        c.ok(r[0] == 422, f"a template bundling {code} is refused", (r[0], message(r[1])))
        if r[0] == 201:
            sc.templates.append((a, data(r[1])["id"]))
    c.eq(roles_of(p, victim["id"], one()), [], "no firm role was written")
    c.eq(global_roles_of(p, victim["id"]), [], "no global role was written")
    # nobody grants themselves anything
    me = data(a.get("/api/v1/me")[1])["id"]
    r = a.put(f"{U}/{me}/firms/{one()}/roles", {"ids": [sc.role_id("FIRM_ADMIN")]})
    c.ok(r[0] in (403, 422), "a firm admin cannot re-grant own roles to themselves", (r[0], message(r[1])))
    seller = api("seller")
    sid = data(seller.get("/api/v1/me")[1])["id"]
    r = seller.put(f"{U}/{sid}/firms/{one()}/roles", {"ids": [sc.role_id("FIRM_ADMIN")]})
    c.eq(r[0], 403, "a seller cannot grant themselves FIRM_ADMIN")
    r = seller.put(f"{U}/{sid}/roles", {"ids": [sc.role_id("FIRM_ADMIN")]})
    c.eq(r[0], 403, "nor globally")
    c.eq(seller.get(U)[0], 403, "and is still a seller")
finally:
    sc.cleanup()
c.done()
