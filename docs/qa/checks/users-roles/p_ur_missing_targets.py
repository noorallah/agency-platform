"""Probe: hiring into a firm that does not exist, and acting on a soft-deleted user.

A hire into a soft-deleted *firm* is not driven: it needs a firm made for the
purpose and left behind (the registry keeps a deleted firm's code).
"""
from _ur import *

c = Check("p_ur_missing_targets"); sc = Scene()
try:
    a, p = sc.admin, sc.platform
    u = sc.user("target")
    for who, api_ in (("platform admin", p), ("firm admin", a)):
        r = api_.put(f"{U}/{u['id']}/firms", {"assignments": [assignment(BAD_ID, True)]})
        c.ok(r[0] in (404, 422), f"{who}: an unknown firm id in a membership write is refused (not 500)", (r[0], message(r[1])))
        r = api_.put(f"{U}/{u['id']}/firms/{BAD_ID}/roles", {"ids": [sc.role_id("CASHIER")]})
        c.ok(r[0] in (404, 422), f"{who}: roles in an unknown firm are refused", (r[0], message(r[1])))
    c.ok(p.put(f"{U}/{u['id']}/roles", {"ids": [BAD_ID]})[0] in (404, 422), "an unknown role id is refused")
    c.ok(a.put(f"{U}/{u['id']}/firms/{one()}/roles", {"ids": [BAD_ID]})[0] in (404, 422), "an unknown role id in a firm is refused")
    # a soft-deleted user is gone for a firm admin and cannot be given roles
    c.eq(a.delete(f"{U}/{u['id']}")[0], 204, "delete")
    for method, path, body in (("GET", f"{U}/{u['id']}", None), ("PATCH", f"{U}/{u['id']}", {"full_name": "Zombie"}),
                               ("PUT", f"{U}/{u['id']}/firms/{one()}/roles", {"ids": [sc.role_id("CASHIER")]}),
                               ("POST", f"{U}/{u['id']}/apply-template", {"template_id": sc.template("counter-sales")["id"]}),
                               ("POST", f"{U}/{u['id']}/clone", {"email": f"z.{sc.tag}@qa.test".lower(), "full_name": "z", "password": PW})):
        st, resp = a.call(method, path, body)
        c.eq(st, 404, f"firm admin: {method} {path.split('/users/')[1][37:] or 'user'} on a deleted user")
    c.eq(roles_of(p, u["id"], one()), [], "no role was written for the deleted user")
finally:
    sc.cleanup()
c.done()
