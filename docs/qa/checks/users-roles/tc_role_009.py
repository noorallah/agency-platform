"""TC-ROLE-009: deleting a role somebody holds just goes through (recorded behaviour)."""
from _ur import *
from _roles import night_desk

c = Check("tc_role_009"); sc = Scene()
try:
    role = night_desk(sc)
    holder = sc.user("holder")
    must(sc.admin.put(f"{U}/{holder['id']}/firms/{one()}/roles", {"ids": [role["id"]]}), "give the role")
    u = sc.sign_in(holder)
    c.eq(u.get("/api/v1/customers")[0], 200, "the holder works")
    c.eq(sc.admin.delete(f"{R}/{role['id']}")[0], 204, "the role deletes without a refusal")
    sc.roles.clear()
    c.eq(u.get("/api/v1/customers")[0], 401, "signed out on the click")
    u2 = sc.sign_in(holder)
    c.eq(u2.get("/api/v1/customers")[0], 403, "signed back in, nothing is offered")
    c.eq(u2.get("/api/v1/receipts")[0], 403, "not even Receipts")
    c.eq(u2.get("/api/v1/me")[0], 200, "but the account itself works")
finally:
    sc.cleanup()
c.done()
