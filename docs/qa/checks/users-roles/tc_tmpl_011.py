"""TC-TMPL-011: a template cannot bundle a platform role."""
from _ur import *

c = Check("tc_tmpl_011"); sc = Scene()
try:
    pa = [r for r in all_rows(sc.platform, f"{R}?search=PLATFORM_ADMIN") if r["code"] == "PLATFORM_ADMIN"]
    c.eq(len(pa), 1, "the platform admin finds the PLATFORM_ADMIN role")
    code = f"qa-bad-{sc.tag.lower()}"
    r = sc.admin.post(T, {"code": code, "name": "Bad", "role_ids": [pa[0]["id"]]})
    c.refused(r, 422, "A template cannot bundle platform or cross-firm roles", "bundle PLATFORM_ADMIN")
    c.ok(code not in [x["code"] for x in all_rows(sc.admin, T)], "nothing was created")
    # also not through an update of an own template
    tpl = sc.new_template(sc.admin, [sc.role_id("CASHIER")])
    r = sc.admin.call("PATCH", f"{T}/{tpl['id']}", {"role_ids": [pa[0]["id"]]})
    c.refused(r, 422, "platform or cross-firm roles", "edit a template to bundle PLATFORM_ADMIN")
    c.eq(data(sc.admin.get(f"{T}/{tpl['id']}")[1])["role_codes"], ["CASHIER"], "the bundle is unchanged")
finally:
    sc.cleanup()
c.done()
