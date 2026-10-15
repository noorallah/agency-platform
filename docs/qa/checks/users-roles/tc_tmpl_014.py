"""TC-TMPL-014: a job offered to every firm is the platform to change."""
from _ur import *

c = Check("tc_tmpl_014"); sc = Scene()
try:
    p, a = sc.platform, sc.admin
    tpl = sc.new_template(p, [sc.role_id("CASHIER")])
    c.eq(p.call("PATCH", f"{T}/{tpl['id']}", {"name": "Every Night 2"})[0], 200, "the platform admin may edit")
    listed = {r["code"]: r for r in all_rows(a, T)}
    c.ok(tpl["code"] in listed, "listed for a firm admin")
    msg = "offered to every firm"
    c.refused(a.call("PATCH", f"{T}/{tpl['id']}", {"name": "y"}), 422, msg, "firm admin PATCH")
    c.refused(a.delete(f"{T}/{tpl['id']}"), 422, msg, "firm admin DELETE")
    c.eq(p.delete(f"{T}/{tpl['id']}")[0], 200, "the platform admin deletes it")
    sc.templates.clear()
    c.ok(tpl["code"] not in [r["code"] for r in all_rows(a, T)], "gone from the firm list")
finally:
    sc.cleanup()
c.done()
