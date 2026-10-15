"""TC-LOOK-003: their profile is not yours; their roles here are (server half)."""
from _ur import *

c = Check("tc_look_003"); sc = Scene()
try:
    a = sc.admin
    out = outsider(sc)
    a.put(f"{U}/{out['id']}/firms", {"assignments": [assignment(one())]})
    a.post(f"{U}/{out['id']}/apply-template", {"template_id": sc.template("counter-sales")["id"]})
    row = data(a.get(f"{U}/{out['id']}")[1])
    c.eq(row.get("belongs_to_other_firms"), True, "the row says they also work elsewhere (screen opens read-only)")
    st, body = a.call("PATCH", f"{U}/{out['id']}", {"full_name": "Renamed"})
    c.ok(st in (403, 409, 422), "a firm admin cannot edit the profile", (st, message(body)))
    r = a.post(f"{U}/{out['id']}/apply-template", {"template_id": sc.template("warehouse")["id"]})
    c.eq(r[0], 200, "apply job template works")
    c.eq(codes(sc, roles_of(a, out["id"], one())), ["INVENTORY_MANAGER"], "their TEST01 roles are replaced")
    c.eq(codes(sc, roles_of(sc.platform, out["id"], two())), ["CASHIER"], "TEST02 roles untouched")
    c.eq(sc.platform.call("PATCH", f"{U}/{out['id']}", {"full_name": f"Platform edit {sc.tag}"})[0], 200,
         "the platform admin can edit the profile")
finally:
    sc.cleanup()
c.done()
