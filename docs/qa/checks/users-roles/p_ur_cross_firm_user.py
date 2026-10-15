"""Probe: a TEST01 firm administrator acting on a TEST02-only user."""
from _ur import *

c = Check("p_ur_cross_firm_user"); sc = Scene()
try:
    a = sc.admin
    t2 = sc.user("t2only", (two(),))
    for method, path, body in (("GET", f"{U}/{t2['id']}", None), ("PATCH", f"{U}/{t2['id']}", {"full_name": "Taken"}),
                               ("DELETE", f"{U}/{t2['id']}", None),
                               ("PUT", f"{U}/{t2['id']}/roles", {"ids": []}),
                               ("GET", f"{U}/{t2['id']}/roles", None),
                               ("GET", f"{U}/{t2['id']}/global-roles", None),
                               ("POST", f"{U}/{t2['id']}/apply-template", {"template_id": sc.template("counter-sales")["id"]}),
                               ("POST", f"{U}/{t2['id']}/clone", {"email": f"c.{sc.tag}@qa.test".lower(), "full_name": "c", "password": PW}),
                               ("POST", f"{U}/{t2['id']}/password", {"new_password": "Brand@New12345"}),
                               ("POST", f"{U}/{t2['id']}/restore", None)):
        st, resp = a.call(method, path, body)
        c.ok(st in (403, 404), f"{method} {path.split(t2['id'])[1] or '/'} is refused", (st, message(resp)))
    c.eq(a.get(f"{U}/{t2['id']}/firms")[1]["data"], [], "memberships read as empty")
    c.eq(len(data(a.get(f"{U}?search={t2['email']}")[1])), 0, "not in the list")
    r = a.put(f"{U}/{t2['id']}/firms", {"assignments": [assignment(one())]})
    c.ok(r[0] in (200, 404, 403, 422), "adding them is the lookup path (allowed or refused, never a 500)", r[0])
    if r[0] == 200:
        c.ok(True, "a TEST01 admin may adopt a TEST02-only user by id (this is what Add existing user does)")
    c.eq(data(sc.platform.get(f"{U}/{t2['id']}")[1])["full_name"], f"t2only {sc.tag}", "the name was not changed")
finally:
    sc.cleanup()
c.done()
