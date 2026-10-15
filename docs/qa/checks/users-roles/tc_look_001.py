"""TC-LOOK-001: looking somebody up (a firm administrator)."""
from _ur import *

c = Check("tc_look_001"); sc = Scene()
try:
    a = sc.admin
    out = outsider(sc)
    member = sc.user("member")
    t = sc.tag.lower()
    c.refused(a.get(f"{U}/lookup?q=t0"), 422, "at least 3 characters", "two characters")
    rows = data(a.get(f"{U}/lookup?q=outsider.{t}")[1])
    c.eq([r["email"] for r in rows], [out["email"]], "found by email")
    c.ok(all(set(r) == {"id", "full_name", "email", "already_a_member"} for r in rows), "no firm is named on a result", rows)
    rows = data(a.get(f"{U}/lookup?q=outsider%20{sc.tag}")[1])
    c.eq([r["email"] for r in rows], [out["email"]], "found by name")
    rows = data(a.get(f"{U}/lookup?q={t}")[1])
    flags = {r["email"]: r["already_a_member"] for r in rows}
    c.eq(flags.get(out["email"]), False, "the outsider is offered")
    c.eq(flags.get(member["email"]), True, "a member of the firm is marked Already in this firm")
    c.eq(data(a.get(f"{U}/lookup?q=zzqq-nobody")[1]), [], "nobody matches")
finally:
    sc.cleanup()
c.done()
