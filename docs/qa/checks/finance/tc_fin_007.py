"""TC-FIN-007: cost and profit centres, and an account that demands one."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _fin import *

c = Check("tc_fin_007")
a = admin()
viewer = admin("viewer")
tag = suffix(4)
CC, PC = f"{FIN}/cost-centers", f"{FIN}/profit-centers"
c.eq(viewer.post(CC, {"code": f"S{tag}", "name": "Sales"})[0], 403, "a Viewer cannot make a cost centre")
st, made = a.post(CC, {"code": f"S{tag}", "name": "Sales"})
c.eq(st, 201, "a cost centre is saved")
cc = data(made)
c.eq(a.post(CC, {"code": f"S{tag}", "name": "Sales"})[0], 409, "the same code again: 409")
c.refused(a.post(CC, {"code": f"S{tag}", "name": "Sales"}), 409, "already exists", "and says a cost centre with this code already exists")
pc = data(a.post(PC, {"code": f"N{tag}", "name": "North"})[1])
c.ok(pc.get("id"), "a profit centre is saved")
c.ok(a.delete(f"{CC}/{cc['id']}")[0] in (404, 405), "no Delete on a cost centre")
c.ok(a.delete(f"{PC}/{pc['id']}")[0] in (404, 405), "no Delete on a profit centre")
c.eq(a.call("PATCH", f"{CC}/{cc['id']}", {"is_active": False})[0], 200, "a cost centre deactivates with Active")
c.eq(a.call("PATCH", f"{CC}/{cc['id']}", {"is_active": True})[0], 200, "and activates again")

purch = account(a, "5000")
AC = f"{FIN}/ledger-accounts/{purch['id']}"
try:
    c.eq(a.call("PATCH", AC, {"requires_cost_center": True})[0], 200, "5000 Purchases is switched to require a cost centre")
    body = draft_body(a, [("5000", "20.00", "0"), ("1000", "0", "20.00")])
    st, ans = a.post(JE, body)
    c.eq(st, 422, "a 5000 line with no cost centre is refused")
    c.ok("requires a cost centre" in message(ans).lower() and "5000" in message(ans), "the refusal names 5000 and the cost centre", message(ans))
    with_cc = draft_body(a, [("5000", "20.00", "0"), ("1000", "0", "20.00")])
    with_cc["lines"][0]["cost_center_id"] = cc["id"]
    st, ans = a.post(JE, with_cc)
    c.eq(st, 201, "with the centre named it saves")
    c.eq(data(ans)["lines"][0]["cost_center_id"], cc["id"], "and keeps the centre on the line")
    inactive = draft_body(a, [("5000", "20.00", "0"), ("1000", "0", "20.00")])
    a.call("PATCH", f"{CC}/{cc['id']}", {"is_active": False})
    inactive["lines"][0]["cost_center_id"] = cc["id"]
    st, ans = a.post(JE, inactive)
    c.ok(st in (409, 422), "a deactivated cost centre cannot be used on a new line", (st, message(ans)))
finally:
    back = a.call("PATCH", AC, {"requires_cost_center": False})
    a.call("PATCH", f"{CC}/{cc['id']}", {"is_active": True})
c.eq(back[0], 200, "the flag is unticked again")
st, ans = a.post(JE, draft_body(a, [("5000", "20.00", "0"), ("1000", "0", "20.00")]))
c.eq(st, 201, "with the flag off a 5000 line saves without a centre")
c.done()
