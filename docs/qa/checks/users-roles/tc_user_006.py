"""TC-USER-006: a firm outside your reach is refused by name."""
from _ur import *

c = Check("tc_user_006"); sc = Scene()
try:
    sh = shared(sc)
    r = sc.admin.put(f"{U}/{sh['id']}/firms", {"assignments": [assignment(BAD_ID)]})
    c.refused(r, 422, "You can only assign firms you administer", "an id that is not the admin firm")
    r = sc.admin.put(f"{U}/{sh['id']}/firms", {"assignments": [assignment(two())]})
    c.refused(r, 422, "You can only assign firms you administer", "TEST02 (real, but not theirs)")
finally:
    sc.cleanup()
c.done()
