"""TC-USER-001: New and Edit are a firm administrator's (the server half)."""
from _ur import *

c = Check("tc_user_001"); sc = Scene()
try:
    admin = sc.admin
    c.refused(admin.get("/api/v1/firms"), 403, "permission", "a firm admin does not hold FIRM_VIEW")
    manual = sc.user("manual")
    set_firm_roles(sc, manual["id"], one(), ["SALES_EXECUTIVE", "CUSTOMER_SUPPORT"])
    c.eq(admin.get(f"{U}/{manual['id']}")[0], 200, "firm admin reads a TEST01-only user")
    st, body = admin.call("PATCH", f"{U}/{manual['id']}", {"full_name": f"Edited {sc.tag}"})
    c.eq(st, 200, "firm admin edits a TEST01-only user")
    c.eq(data(body)["full_name"] if st == 200 else None, f"Edited {sc.tag}", "the edit is stored")
    made = admin.post(U, {"email": f"made.{sc.tag}@qa.test".lower(), "full_name": "Made", "password": PW})
    c.eq(made[0], 201, "firm admin creates a user")
    if made[0] == 201:
        sc.users.append(data(made[1])["id"])
        c.eq(data(made[1]).get("belongs_to_other_firms", False), False, "a new user is not shared")
finally:
    sc.cleanup()
c.done()
