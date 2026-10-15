"""TC-HIRE-002: a clone gets the access, not the person."""
from _ur import *

c = Check("tc_hire_002"); sc = Scene()
try:
    a = sc.admin
    src, _ = sc.hire("source", "field-sales")
    # give the source some personal details a clone must not inherit
    sc.platform.call("PATCH", f"{U}/{src['id']}", {"personal_mobile": "+919800000111", "employee_code": f"E{sc.tag}"})
    email = f"clone.{sc.tag}@qa.test".lower()
    st, body = a.post(f"{U}/{src['id']}/clone", {"email": email, "full_name": "Clone Test", "password": "Welcome@12345"})
    c.eq(st, 201, "a firm admin can hire like a person who holds a role" + ("" if st == 201 else f" ({message(body)})"))
    if st != 201:  # carry on with the platform route so the rest is still read
        st, body = sc.platform.post(f"{U}/{src['id']}/clone", {"email": email, "full_name": "Clone Test", "password": "Welcome@12345"})
        c.eq(st, 201, "the platform route creates the clone")
    new = data(body)
    sc.users.append(new["id"])
    c.eq(new["force_password_change"], True, "must change the password on first sign-in")
    c.eq(new.get("personal_mobile"), None, "blank mobile")
    c.eq(new.get("employee_code"), None, "blank employee code")
    c.eq(codes(sc, roles_of(a, new["id"], one())), ["SALES_EXECUTIVE"], "the same role in TEST01")
    ms = data(sc.platform.get(f"{U}/{new['id']}/firms")[1])
    c.eq([(m["firm_id"], m["is_primary"]) for m in ms], [(one(), True)], "TEST01 as the primary firm")
    u = sign_in(email, "Welcome@12345", one())
    c.eq(u.get("/api/v1/customers")[0], 403, "nothing else opens before the password is changed")
    r = u.post("/api/v1/auth/change-password", {"current_password": "Welcome@12345", "new_password": "CloneTest@2026x"})
    c.eq(r[0] in (200, 204), True, "the password can be changed")
    u2 = sign_in(email, "CloneTest@2026x", one())
    c.eq(u2.get("/api/v1/customers")[0], 200, "afterwards the source access works")
    c.eq(u2.get(U)[0], 403, "and there is no Platform part")
finally:
    sc.cleanup()
c.done()
