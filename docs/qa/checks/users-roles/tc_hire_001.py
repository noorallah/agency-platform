"""TC-HIRE-001: the clone dialog, and what the server refuses."""
from _ur import *

c = Check("tc_hire_001"); sc = Scene()
try:
    a = sc.admin
    src, _ = sc.hire("source", "field-sales")
    path = f"{U}/{src['id']}/clone"
    c.eq(a.post(path, {})[0], 422, "an empty form is refused")
    r = a.post(path, {"email": f"clone.{sc.tag}@qa.test".lower(), "full_name": "Clone Test", "password": "short"})
    c.refused(r, 422, "password", "short password")
    c.ok("12" in message(r[1]) or "least" in message(r[1]).lower(), "the reasons name the length rule", message(r[1]))
    r = a.post(path, {"email": "not-an-email", "full_name": "Clone Test", "password": "Welcome@12345"})
    c.ok(r[0] == 422, "an address that is not an email is refused by the server too", (r[0], message(r[1])))
    c.eq(len(data(a.get(f"{U}?search=clone.{sc.tag.lower()}")[1])), 0, "nothing was created")
finally:
    sc.cleanup()
c.done()
