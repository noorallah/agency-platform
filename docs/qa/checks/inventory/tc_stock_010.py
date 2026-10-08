"""TC-STOCK-010: why stock is issued: each reason posts to its own account."""
from _inv import *
from _flow import *

c = Check("tc_stock_010")
w = World()
wh = w.warehouse()
p = w.product()
w.stock_in(wh["id"], p["id"], 50)
accounts = control_accounts(w)
base = {"branch_id": w.branch_id, "warehouse_id": wh["id"], "product_id": p["id"], "transaction_date": w.today}
want = {"INTERNAL_USE": "INTERNAL_USE", "STAFF": "STAFF_WELFARE", "DISPLAY": "SAMPLES_AND_DISPLAY", "DAMAGE": "INVENTORY_ADJUSTMENT"}
for reason, purpose in want.items():
    ref = f"R{reason[:3]}-{w.tag}"
    st, b = w.admin.post(f"{INV}/write-offs", {**base, "quantity": "2", "reason": reason, "reference_number": ref})
    c.ok(st in (200, 201), f"{reason} write-off accepted", (st, message(b)))
    js = entries(w, ref)
    if c.eq(len(js), 1, f"{reason}: one journal"):
        net = by_purpose(w, js[0])
        c.eq(net.get(purpose), D(120), f"{reason}: Dr {purpose} 120")
        c.eq(net.get("INVENTORY"), D(-120), f"{reason}: Cr inventory 120")
c.eq(w.qty(p["id"]), D(42), "4 write-offs of 2 leave 42")
# a firm's own reason, with its own expense account
code = f"GIFT{w.tag}"
st, b = w.admin.post(f"{INV}/adjustment-reasons", {"code": code, "name": "Festival gift", "ledger_account_id": accounts["PROMOTIONAL_EXPENSE"]})
c.ok(st in (200, 201), "own reason created", (st, message(b)))
ref = f"RG-{w.tag}"
st, b = w.admin.post(f"{INV}/write-offs", {**base, "quantity": "1", "reason": code, "reference_number": ref})
c.ok(st in (200, 201), "write-off with the new reason", (st, message(b)))
js = entries(w, ref)
if c.eq(len(js), 1, "own reason: one journal"):
    c.eq(by_purpose(w, js[0]).get("PROMOTIONAL_EXPENSE"), D(60), "posts to the reason's own account")
# deactivate another and it is refused
reasons = {r["code"]: r for r in data(w.admin.get(f"{INV}/adjustment-reasons")[1])}
other = reasons.get(code)
st, b = w.admin.put(f"{INV}/adjustment-reasons/{other['id']}", {"code": code, "name": "Festival gift", "ledger_account_id": accounts["PROMOTIONAL_EXPENSE"], "is_active": False})
c.eq(st, 200, "reason deactivated")
st, b = w.admin.post(f"{INV}/write-offs", {**base, "quantity": "1", "reason": code, "reference_number": ref + "Z"})
c.ok(st in (409, 422), "an inactive reason is refused", (st, message(b)))
st, b = w.admin.post(f"{INV}/write-offs", {**base, "quantity": "1", "reason": "NOSUCH" + w.tag, "reference_number": ref + "Y"})
c.ok(st in (409, 422), "an unknown reason is refused", (st, message(b)))
# an adjustment carries a reason code too
st, b = w.admin.post(f"{INV}/adjustments", {**base, "quantity": "-1", "reason_code": "LOSS", "reference_number": f"ADJ-{w.tag}"})
c.ok(st in (200, 201), "negative adjustment with a reason code", (st, message(b)))
c.eq(w.qty(p["id"]), D(40), "40 after the adjustment")
c.done()
