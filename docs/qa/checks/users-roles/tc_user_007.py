"""TC-USER-007: a firm administrator's membership write merges."""
from _ur import *

c = Check("tc_user_007"); sc = Scene()
try:
    sh = shared(sc)
    r = sc.admin.put(f"{U}/{sh['id']}/firms", {"assignments": [assignment(one())]})
    c.eq(r[0], 200, "naming only your own firm is legitimate")
    ms = {m["firm_id"]: m for m in data(sc.platform.get(f"{U}/{sh['id']}/firms")[1])}
    c.eq(sorted(ms), sorted([one(), two()]), "both memberships survive")
    c.eq(ms.get(two(), {}).get("is_primary"), True, "TEST02 is still primary")
finally:
    sc.cleanup()
c.done()
