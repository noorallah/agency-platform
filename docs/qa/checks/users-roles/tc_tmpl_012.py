"""TC-TMPL-012: a platform administrator chooses who a job is offered to."""
from _ur import *

c = Check("tc_tmpl_012"); sc = Scene()
try:
    p = sc.platform
    c.eq(p.get(T)[0], 200, "the tab opens with no firm selected")
    every = sc.new_template(p, [sc.role_id("CASHIER")])
    c.eq(every["firm_id"], None, "blank Offered to means every firm")
    one_firm = sc.new_template(p, [sc.role_id("CASHIER")], firm_id=two())
    c.eq(one_firm["firm_id"], two(), "naming a firm keeps it on that firm")
    c.eq(one_firm["is_system"], False, "and it is not a system template")
finally:
    sc.cleanup()
c.done()
