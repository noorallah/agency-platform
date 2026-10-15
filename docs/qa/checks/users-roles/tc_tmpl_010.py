"""TC-TMPL-010: retiring a template is a decision about future hires."""
from _ur import *

c = Check("tc_tmpl_010"); sc = Scene()
try:
    a = sc.admin
    tpl = sc.new_template(a, [sc.role_id("CASHIER"), sc.role_id("BILLING_EXECUTIVE")])
    hired = sc.user("nighthire")
    c.eq(a.post(f"{U}/{hired['id']}/apply-template", {"template_id": tpl["id"]})[0], 200, "hire into the template")
    c.eq(a.delete(f"{T}/{tpl['id']}")[0], 200, "retire the template")
    listed = [r["code"] for r in all_rows(a, T)]
    c.ok(tpl["code"] not in listed, "the retired template is not offered")
    c.eq(codes(sc, roles_of(a, hired["id"], one())), ["BILLING_EXECUTIVE", "CASHIER"], "the person keeps the roles")
    c.eq(a.post(f"{U}/{hired['id']}/apply-template", {"template_id": tpl["id"]})[0] in (404, 422), True, "a retired template cannot be applied")
finally:
    sc.cleanup()
c.done()
