"""TC-TMPL-013: a job offered to one firm is not offered to another."""
from _ur import *

c = Check("tc_tmpl_013"); sc = Scene()
try:
    tpl = sc.new_template(sc.platform, [sc.role_id("CASHIER")], firm_id=two())
    c.eq(tpl["firm_id"], two(), "offered to TEST02")
    c.ok(tpl["code"] not in [r["code"] for r in all_rows(sc.admin, T)], "not listed for TEST01 admin")
    st = sc.admin.get(f"{T}/{tpl['id']}")[0]
    c.ok(st in (403, 404), "TEST01 admin cannot read it by id", st)
    r = sc.admin.call("PATCH", f"{T}/{tpl['id']}", {"name": "y"})
    c.ok(r[0] in (403, 404, 422), "nor edit it", (r[0], message(r[1])))
    mine = sc.user("t2hire", (two(),))
    c.eq(sc.admin.post(f"{U}/{mine['id']}/apply-template", {"template_id": tpl["id"]})[0] in (403, 404, 422), True, "nor apply it")
    c.eq(sc.platform.delete(f"{T}/{tpl['id']}")[0], 200, "the platform admin deletes it")
    sc.templates.clear()
finally:
    sc.cleanup()
c.done()
