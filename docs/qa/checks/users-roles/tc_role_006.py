"""TC-ROLE-006: hiring into a template grants exactly its roles."""
from _ur import *
from _roles import night_desk

c = Check("tc_role_006"); sc = Scene()
try:
    role = night_desk(sc)
    tpl = sc.new_template(sc.admin, [role["id"]])
    hire = sc.user("hire")
    c.eq(sc.admin.post(f"{U}/{hire['id']}/apply-template", {"template_id": tpl["id"]})[0], 200, "apply the custom job")
    c.eq(roles_of(sc.admin, hire["id"], one()), [role["id"]], "TEST01 section holds only the custom role")
    c.eq(global_roles_of(sc.platform, hire["id"]), [], "and nothing global")
finally:
    sc.cleanup()
c.done()
