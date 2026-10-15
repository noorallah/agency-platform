"""TC-USER-002: somebody who also works elsewhere: the server refuses the write and says why."""
from _ur import *

c = Check("tc_user_002"); sc = Scene()
try:
    sh = shared(sc)
    t2 = sc.user("t2only", (two(),))
    a = sc.admin
    st, body = a.get(f"{U}/{sh['id']}")
    c.eq(st, 200, "the shared member opens (read) for a firm admin")
    c.eq(data(body).get("belongs_to_other_firms") if st == 200 else None, True, "the row says they work in another firm")
    rows = data(a.get(f"{U}?search={sc.tag.lower()}&page_size=50")[1])
    flags = {r["email"]: r["belongs_to_other_firms"] for r in rows}
    c.eq(flags.get(sh["email"]), True, "the grid row carries the flag")
    st, body = a.call("PATCH", f"{U}/{sh['id']}", {"full_name": "Hijack"})
    c.ok(st in (403, 409, 422), "a firm admin cannot edit somebody who works elsewhere", (st, message(body)))
    c.ok("firm" in message(body).lower() or "platform" in message(body).lower(), "the refusal names the reason", message(body))
    c.ok(a.delete(f"{U}/{sh['id']}")[0] in (403, 409, 422), "nor delete them")
    c.eq(a.get(f"{U}/{t2['id']}")[0], 404, "a TEST02-only user is invisible to TEST01 admin")
    c.eq(data(sc.platform.get(f"{U}/{sh['id']}")[1])["full_name"], f"shared {sc.tag}", "the shared member name is untouched")
finally:
    sc.cleanup()
c.done()
