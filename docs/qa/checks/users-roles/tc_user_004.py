"""TC-USER-004: creating somebody in no firm."""
from _ur import *

c = Check("tc_user_004"); sc = Scene()
try:
    a = sc.admin
    nf = sc.user("nofirm", (), by=a)
    c.eq(a.put(f"{U}/{nf['id']}/firms", {"assignments": []})[0], 200, "clearing the Firms box saves")
    c.eq(data(sc.platform.get(f"{U}/{nf['id']}/firms")[1]), [], "created in no firm")
    c.eq(len(data(a.get(f"{U}?search=nofirm.{sc.tag.lower()}")[1])), 0, "not in the firm admin grid")
    st, body = a.get(f"{U}/lookup?q=nofirm.{sc.tag.lower()}")
    rows = data(body)
    c.eq([r["already_a_member"] for r in rows], [False], "lookup finds them, not marked as a member")
    nf2 = sc.user("nofirm2", (), by=a)
    a.put(f"{U}/{nf2['id']}/firms", {"assignments": []})
    ids = {"ids": [sc.role_id("SALES_EXECUTIVE")]}
    c.refused(sc.platform.put(f"{U}/{nf2['id']}/firms/{one()}/roles", ids), 422,
              "Add the user to this firm", "roles for somebody in no firm (platform admin)")
    c.eq(a.put(f"{U}/{nf2['id']}/firms/{one()}/roles", ids)[0] in (404, 422), True,
         "a firm admin cannot give roles to somebody in no firm")
    c.eq(roles_of(sc.platform, nf2["id"], one()), [], "no role row was written")
    c.ok(all(set(r) == {"id", "full_name", "email", "already_a_member"} for r in rows), "a lookup row names no firm", rows)
finally:
    sc.cleanup()
c.done()
