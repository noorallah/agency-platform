"""TC-HIRE-004: copying access is granting access."""
from _ur import *

c = Check("tc_hire_004"); sc = Scene()
try:
    src, u = sc.hire("source", "field-sales")
    r = u.post(f"{U}/{src['id']}/clone", {"email": f"x.{sc.tag}@qa.test".lower(), "full_name": "x", "password": "Welcome@12345"})
    c.eq(r[0], 403, "a SALES_EXECUTIVE cannot clone (ROLE_ASSIGN)")
    c.eq(len(data(sc.platform.get(f"{U}?search=x.{sc.tag.lower()}")[1])), 0, "nothing was created")
    c.eq(u.get(U)[0], 403, "no Users screen (USER_VIEW)")
finally:
    sc.cleanup()
c.done()
