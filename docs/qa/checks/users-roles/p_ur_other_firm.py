"""Probe: a firm administrator writing a role (or reading people) into another firm."""
from _ur import *

c = Check("p_ur_other_firm"); sc = Scene()
try:
    a2 = sc.admin.inside(two())  # TEST01 admin, but naming TEST02 in X-Firm-ID
    code = f"qa-x2-{sc.tag.lower()}"
    r = a2.post(R, {"code": code, "name": "Into TEST02"})
    c.eq(r[0], 403, "creating a role with another firm in X-Firm-ID")
    if r[0] == 201:
        sc.roles.append((a2, data(r[1])["id"]))
    c.ok(code not in [x["code"] for x in all_rows(sc.platform.inside(two()), R)], "no role appeared in TEST02")
    for path in (U, R, T, "/api/v1/permissions"):
        c.eq(a2.get(path)[0], 403, f"GET {path} naming TEST02")
    r = sc.admin.post(R, {"code": f"qa-body-{sc.tag.lower()}", "name": "x", "firm_id": two()})
    c.eq(r[0], 422, "a firm_id in the role body is not a field")
    if r[0] == 201:
        sc.roles.append((sc.admin, data(r[1])["id"]))
    r = a2.post(U, {"email": f"x2.{sc.tag}@qa.test".lower(), "full_name": "x", "password": PW})
    c.eq(r[0], 403, "creating a user naming TEST02")
    if r[0] == 201:
        sc.users.append(data(r[1])["id"])
finally:
    sc.cleanup()
c.done()
