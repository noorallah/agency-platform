"""TC-ROLE-005: a template can bundle the firm own custom role."""
from _ur import *
from _roles import night_desk

c = Check("tc_role_005"); sc = Scene()
try:
    role = night_desk(sc)
    tpl = sc.new_template(sc.admin, [role["id"]], code=f"qa-my-job-{sc.tag.lower()}")
    c.eq((tpl["firm_id"], tpl["is_system"]), (one(), False), "Origin: this firm")
    c.eq(tpl["role_ids"], [role["id"]], "it bundles the custom role")
finally:
    sc.cleanup()
c.done()
