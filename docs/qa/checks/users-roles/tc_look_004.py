"""TC-LOOK-004: adding somebody tells you nothing about their other firms."""
from _ur import *

c = Check("tc_look_004"); sc = Scene()
try:
    a = sc.admin
    out = outsider(sc)
    a.put(f"{U}/{out['id']}/firms", {"assignments": [assignment(one())]})
    a.post(f"{U}/{out['id']}/apply-template", {"template_id": sc.template("counter-sales")["id"]})
    mine = data(a.get(f"{U}/{out['id']}/firms")[1])
    c.eq([m["firm_id"] for m in mine], [one()], "firm admin sees only TEST01")
    both = {m["firm_id"]: m for m in data(sc.platform.get(f"{U}/{out['id']}/firms")[1])}
    c.eq(sorted(both), sorted([one(), two()]), "platform admin sees both")
    c.eq(both[two()]["is_primary"], True, "TEST02 stays primary")
    c.eq(codes(sc, roles_of(sc.platform, out["id"], two())), ["CASHIER"], "TEST02 exactly CASHIER")
    c.eq(codes(sc, roles_of(sc.platform, out["id"], one())), ["BILLING_EXECUTIVE", "CASHIER"], "TEST01 from Counter Sales")
finally:
    sc.cleanup()
c.done()
