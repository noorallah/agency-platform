"""TC-TMPL-015: a firm administrator cannot write a template for another firm."""
from _ur import *

c = Check("tc_tmpl_015"); sc = Scene()
try:
    a = sc.admin
    for firm in (BAD_ID, two()):
        code = f"qa-x-{sc.tag.lower()}"
        r = a.post(T, {"code": code, "name": "X", "firm_id": firm, "role_ids": [sc.role_id("CASHIER")]})
        c.refused(r, 422, "You can only act within your own firm", f"firm_id {firm[:8]}")
        c.ok(code not in [x["code"] for x in all_rows(sc.platform, T)], "nothing created")
    # naming their own firm is fine
    own = a.post(T, {"code": f"qa-own-{sc.tag.lower()}", "name": "Own", "firm_id": one(), "role_ids": [sc.role_id("CASHIER")]})
    if own[0] == 201:
        sc.templates.append((a, data(own[1])["id"]))
    c.eq(own[0], 201, "naming their own firm is accepted")
finally:
    sc.cleanup()
c.done()
