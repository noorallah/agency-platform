"""TC-USER-008: a firm administrator does not move somebody's primary firm."""
from _ur import *

c = Check("tc_user_008"); sc = Scene()
try:
    sh = shared(sc)
    r = sc.admin.put(f"{U}/{sh['id']}/firms", {"assignments": [assignment(one(), primary=True)]})
    c.eq(r[0], 200, "the write is accepted")
    ms = {m["firm_id"]: m for m in data(sc.platform.get(f"{U}/{sh['id']}/firms")[1])}
    c.eq(ms[two()]["is_primary"], True, "primary is still TEST02")
    c.eq(ms[one()]["is_primary"], False, "TEST01 was not made primary")
    nf = sc.user("noprimary", (), by=sc.admin)
    sc.admin.put(f"{U}/{nf['id']}/firms", {"assignments": [assignment(one())]})
    ms = data(sc.platform.get(f"{U}/{nf['id']}/firms")[1])
    c.eq([m["is_primary"] for m in ms], [True], "somebody with no primary gets one")
finally:
    sc.cleanup()
c.done()
