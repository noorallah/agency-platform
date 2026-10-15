"""TC-FIN-001: a new ledger account, and what cannot change afterwards."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import random

from _fin import *

c = Check("tc_fin_001")
a = admin()
viewer = admin("viewer")
groups = {g["code"]: g for g in rows_of(a.get(f"{FIN}/account-groups?page_size=100"))}
code = str(random.randint(9000, 9899))
body = {"code": code, "name": f"Manual test account {code}", "account_type": "EXPENSE", "account_group_id": groups["REV"]["id"]}
c.refused(a.post(f"{FIN}/ledger-accounts", body), 422, "must share its group's account type", "type EXPENSE in group REV is refused")
c.ok(not [x for x in rows_of(a.get(f"{FIN}/ledger-accounts?page_size=200")) if x["code"] == code], "and no row was made")
c.eq(viewer.post(f"{FIN}/ledger-accounts", {**body, "account_group_id": groups["EXP"]["id"]})[0], 403, "a Viewer cannot create an account")
st, made = a.post(f"{FIN}/ledger-accounts", {**body, "account_group_id": groups["EXP"]["id"]})
c.eq(st, 201, "type EXPENSE in group EXP saves")
acc = data(made)
c.eq((acc["code"], acc["account_type"], acc["is_active"]), (code, "EXPENSE", True), "code, type, active")
c.refused(a.post(f"{FIN}/ledger-accounts", {**body, "account_group_id": groups["EXP"]["id"]}), 409, "already exists", "the same code again is refused")
AC = f"{FIN}/ledger-accounts/{acc['id']}"
c.ok(a.delete(AC)[0] in (404, 405), "there is no Delete on an account")
# what can change
ok = a.call("PATCH", AC, {"name": "Renamed test account", "description": "d", "requires_cost_center": True, "requires_profit_center": True, "is_active": False})
c.eq(ok[0], 200, "name, description, the two Requires flags and Active change")
got = data(ok[1])
c.eq((got["name"], got["requires_cost_center"], got["requires_profit_center"], got["is_active"]), ("Renamed test account", True, True, False), "and read back")
# what cannot
c.eq(a.call("PATCH", AC, {"code": "9998"})[0], 422, "the code is not a field of the update")
c.eq(a.call("PATCH", AC, {"account_type": "ASSET"})[0], 422, "nor is the type")
moved = a.call("PATCH", AC, {"account_group_id": groups["CA"]["id"]})
c.ok(moved[0] in (409, 422), "moving it to a group of another type is refused", (moved[0], message(moved[1])))
again = data(a.get(AC)[1]) if a.get(AC)[0] == 200 else None
if again is None:
    again = next(x for x in rows_of(a.get(f"{FIN}/ledger-accounts?page_size=200")) if x["id"] == acc["id"])
c.eq(again["account_group_id"], groups["EXP"]["id"], "the group is unchanged")
c.eq(again["account_type"], "EXPENSE", "the type is unchanged")
c.done()
