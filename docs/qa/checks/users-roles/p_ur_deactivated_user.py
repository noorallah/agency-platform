"""Probe: a deactivated or deleted user cannot keep working on the token they hold."""
from _ur import *

c = Check("p_ur_deactivated_user"); sc = Scene()
try:
    a = sc.admin
    row, u = sc.hire("leaver", "counter-sales")
    c.eq(u.post("/api/v1/receipts", {})[0], 422, "works before")
    c.eq(a.call("PATCH", f"{U}/{row['id']}", {"is_active": False})[0], 200, "deactivate")
    st = u.post("/api/v1/receipts", {})[0]
    c.ok(st in (401, 403), "the old token stops working at once", st)
    st, body = Api().post("/api/v1/auth/login", {"email": row["email"], "password": PW})
    c.ok(st in (401, 403), "and sign-in is refused", (st, message(body)))
    c.eq(a.call("PATCH", f"{U}/{row['id']}", {"is_active": True})[0], 200, "reactivate")
    u2 = sc.sign_in(row)
    c.eq(u2.post("/api/v1/receipts", {})[0], 422, "back at work with the same roles")
    c.eq(a.delete(f"{U}/{row['id']}")[0], 204, "delete")
    sc.users.clear()
    c.ok(u2.post("/api/v1/receipts", {})[0] in (401, 403), "a deleted user token stops working")
    st, body = Api().post("/api/v1/auth/login", {"email": row["email"], "password": PW})
    c.ok(st in (401, 403), "and cannot sign in", (st, message(body)))
finally:
    sc.cleanup()
c.done()
