"""TC-LOOK-002: adding somebody who already has an account, with a job."""
from _ur import *

c = Check("tc_look_002"); sc = Scene()
try:
    a = sc.admin
    out = outsider(sc)
    r = a.put(f"{U}/{out['id']}/firms", {"assignments": [assignment(one())]})
    c.eq(r[0], 200, "the membership write (merges)")
    r = a.post(f"{U}/{out['id']}/apply-template", {"template_id": sc.template("counter-sales")["id"]})
    c.eq(r[0], 200, "the job is applied")
    grid = data(a.get(f"{U}?search=outsider.{sc.tag.lower()}")[1])
    c.eq(len(grid), 1, "they appear in TEST01 grid")
    c.eq(codes(sc, roles_of(a, out["id"], one())), ["BILLING_EXECUTIVE", "CASHIER"], "their TEST01 roles")
finally:
    sc.cleanup()
c.done()
