"""TC-USER-003: New starts in the firm that is open; the firm list is /me/firms."""
from _ur import *

c = Check("tc_user_003"); sc = Scene()
try:
    a = sc.admin
    mine = data(a.get("/api/v1/me/firms")[1])
    c.ok(one() in [str(r["id"]) for r in mine], "me/firms offers the admin own firm")
    c.ok(two() not in [str(r["id"]) for r in mine], "me/firms does not offer a firm the admin is not in")
    c.eq(a.get("/api/v1/firms")[0], 403, "/firms is platform-only for a firm admin")
    st, body = a.post(U, {"email": f"infirm.{sc.tag}@qa.test".lower(), "full_name": "In Firm", "password": PW})
    c.eq(st, 201, "created")
    if st == 201:
        uid = data(body)["id"]
        sc.users.append(uid)
        ms = data(sc.platform.get(f"{U}/{uid}/firms")[1])
        c.eq([m["firm_id"] for m in ms], [one()], "created in TEST01 (the firm open) and nowhere else")
        found = data(a.get(f"{U}?search=infirm.{sc.tag.lower()}")[1])
        c.eq(len(found), 1, "in the grid at once")
finally:
    sc.cleanup()
c.done()
