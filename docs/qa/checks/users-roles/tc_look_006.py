"""TC-LOOK-006: a platform administrator gets the directory."""
from _ur import *

c = Check("tc_look_006"); sc = Scene()
try:
    p = sc.platform.inside(one())
    out = outsider(sc)
    t = sc.tag.lower()
    st, body = p.get(f"{U}/lookup?q=&page=1&page_size=2")
    c.eq(st, 200, "an empty term is allowed for a platform caller")
    c.eq(len(data(body)), 2, "two rows on the page")
    c.ok(body["pagination"]["total_records"] > 2, "total_records counts everybody not in TEST01", body.get("pagination"))
    mails = [r["email"] for r in all_rows(p, f"{U}/lookup?q=", 50)]
    c.ok(out["email"] in mails, "the outsider is listed")
    c.ok(not any(m in (state(MODULE)["accounts"]["admin"]["email"], state(MODULE)["accounts"]["platform"]["email"]) for m in mails), "members and platform admins are left out")
    c.eq(len(data(p.get("%s/lookup?q=e" % U)[1])) > 0, True, "one character filters for a platform caller")
    p.put(f"{U}/{out['id']}/firms", {"assignments": [assignment(one()), assignment(two(), True)]})
    rows = data(p.get(f"{U}/lookup?q=outsider.{t}")[1])
    c.eq(rows, [], "once added, a platform caller directory excludes them")
finally:
    sc.cleanup()
c.done()
