"""TC-LOOK-005: reaching across firms is not reading your own people."""
from _ur import *

c = Check("tc_look_005"); sc = Scene()
try:
    seller = api("seller")
    c.eq(seller.get(f"{U}/lookup?q=fixtures")[0], 403, "a seller is refused the lookup (USER_CREATE, not USER_VIEW)")
    a = sc.admin
    c.refused(a.get(f"{U}/lookup?q="), 422, "at least 3 characters", "an empty term")
    page2 = data(a.get(f"{U}/lookup?q=qa.test&page=2&page_size=2")[1])
    c.eq(page2, [], "page 2 is empty for a firm caller")
    plain = data(a.get(f"{U}/lookup?q=qa.test")[1])
    c.ok(len(plain) <= 10, "a plain lookup returns at most 10", len(plain))
    big = data(a.get(f"{U}/lookup?q=qa.test&page_size=100")[1])
    c.ok(len(big) <= 10, "page_size does not lift the cap of 10", len(big))
finally:
    sc.cleanup()
c.done()
