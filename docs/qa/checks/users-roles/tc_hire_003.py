"""TC-HIRE-003: a clone is a starting point, not a link."""
from _ur import *

c = Check("tc_hire_003"); sc = Scene()
try:
    a = sc.admin
    src, _ = sc.hire("source", "field-sales")
    st, body = a.post(f"{U}/{src['id']}/clone", {"email": f"clone2.{sc.tag}@qa.test".lower(), "full_name": "Clone Two", "password": "Welcome@12345"})
    c.eq(st, 201, "a firm admin can hire like a person who holds a role" + ("" if st == 201 else f" ({message(body)})"))
    if st != 201:
        st, body = sc.platform.post(f"{U}/{src['id']}/clone", {"email": f"clone2.{sc.tag}@qa.test".lower(), "full_name": "Clone Two", "password": "Welcome@12345"})
    new = data(body)
    sc.users.append(new["id"])
    set_firm_roles(sc, new["id"], one(), ["SALES_EXECUTIVE", "CUSTOMER_SUPPORT"], by=a)
    c.eq(codes(sc, roles_of(a, new["id"], one())), ["CUSTOMER_SUPPORT", "SALES_EXECUTIVE"], "the clone holds both")
    c.eq(codes(sc, roles_of(a, src["id"], one())), ["SALES_EXECUTIVE"], "the source still holds exactly SALES_EXECUTIVE")
finally:
    sc.cleanup()
c.done()
