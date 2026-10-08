"""Probe: adjustment reasons: system reasons are protected, codes are unique, and a reason's account must be an expense."""
from _inv import *
from _flow import *

c = Check("p_reasons")
w = World()
acc = control_accounts(w)
R = f"{INV}/adjustment-reasons"
rs = {r["code"]: r for r in data(w.admin.get(R)[1])}
sysr = rs["DAMAGE"]
st, b = w.admin.delete(f"{R}/{sysr['id']}")
c.ok(400 <= st < 500, "a system reason cannot be deleted", (st, message(b)))
st, b = w.admin.put(f"{R}/{sysr['id']}", {"code": "RENAMED", "name": "Damage"})
c.ok(400 <= st < 500, "a system reason's code cannot change", (st, message(b)))
code = f"RS{w.tag}"
st, b = w.admin.post(R, {"code": code, "name": "Mine"})
c.eq(st, 201, "own reason created")
mine = data(b)
st, b = w.admin.post(R, {"code": code.lower(), "name": "Mine again"})
c.ok(st in (409, 422), "the same code in lower case is a duplicate", (st, message(b)))
st, b = w.admin.post(R, {"code": "DAMAGE", "name": "Dup"})
c.ok(st in (409, 422), "a system code cannot be reused", (st, message(b)))
for purpose in ("CASH", "ACCOUNTS_PAYABLE", "SALES_REVENUE", "INVENTORY"):
    st, b = w.admin.post(R, {"code": f"X{purpose[:4]}{w.tag}", "name": f"on {purpose}", "ledger_account_id": acc[purpose]})
    c.ok(st in (409, 422), f"a reason pointed at the {purpose} account is refused (it expects an expense account)", (st, message(b)))
st, b = w.admin.post(R, {"code": f"XB{w.tag}", "name": "bad account", "ledger_account_id": "00000000-0000-4000-8000-000000000001"})
c.ok(400 <= st < 500, "an unknown account id is refused", (st, message(b)))
# use it, then try to delete
a = w.warehouse()
p = w.product()
w.stock_in(a["id"], p["id"], 5)
w.admin.put(f"{R}/{mine['id']}", {"code": code, "name": "Mine", "ledger_account_id": acc["PROMOTIONAL_EXPENSE"]})
st, b = w.admin.post(f"{INV}/write-offs", {"branch_id": w.branch_id, "warehouse_id": a["id"], "product_id": p["id"], "transaction_date": w.today,
                                          "quantity": "1", "reason": code, "reference_number": f"U{w.tag}"})
c.eq(st, 201, "the reason is used")
st, b = w.admin.delete(f"{R}/{mine['id']}")
c.ok(st in (200, 204, 409, 422), "deleting a used reason is answered cleanly", (st, message(b)))
c.done()
