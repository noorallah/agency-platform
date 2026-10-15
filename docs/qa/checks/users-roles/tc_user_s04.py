"""03-S04 User Templates screen (server half)."""
from _ur import *

c = Check("tc_user_s04"); sc = Scene()
try:
    a = sc.admin
    c.eq(a.get(T)[0], 200, "opens for ROLE_VIEW")
    c.eq(api("seller").get(T)[0], 403, "refused without it")
    tpl = sc.new_template(a, [sc.role_id("CASHIER")])
    c.eq([r["id"] for r in data(a.get(f"{T}?search={tpl['code']}")[1])], [tpl["id"]], "search narrows")
    c.eq(a.get(f"{T}?page_size=101")[0], 422, "page_size cap")
    c.eq(a.post(T, {"code": "ab", "name": "x", "role_ids": []})[0], 422, "an empty bundle is refused")
    c.eq(a.post(T, {"code": tpl["code"], "name": "dup", "role_ids": [sc.role_id("CASHIER")]})[0] in (409, 422), True, "a duplicate code is refused")
    c.eq(a.call("PATCH", f"{T}/{tpl['id']}", {"role_ids": []})[0], 422, "a template cannot be emptied")
    c.eq(data(a.get(f"{T}/{tpl['id']}")[1])["role_codes"], ["CASHIER"], "and it still bundles its role")
finally:
    sc.cleanup()
c.done()
