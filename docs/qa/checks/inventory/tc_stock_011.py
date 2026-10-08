"""TC-STOCK-011: repacking and bulk breaking, wastage, cancel."""
from _inv import *
from _flow import *

c = Check("tc_stock_011")
w = World()
wh = w.warehouse()
bulk = w.product("BULK")
pack = w.product("PACK", purchase_price="15")
w.stock_in(wh["id"], bulk["id"], 50, 60)
RP = f"{INV}/repacks"


def repack(consume: str, produce: str, wastage: str) -> tuple[int, object]:
    """Post a repack of bulk into packs."""
    return w.admin.post(RP, {"repack_date": w.today, "branch_id": w.branch_id, "warehouse_id": wh["id"],
                             "wastage_percent": wastage,
                             "lines": [{"kind": "CONSUME", "product_id": bulk["id"], "quantity": consume},
                                       {"kind": "PRODUCE", "product_id": pack["id"], "quantity": produce}]})


books0 = w.inventory_account()
st, b = repack("10", "40", "1")
c.eq(st, 201, "repack with wastage posted")
r1 = data(b)
c.eq((D(r1["consumed_value"]), D(r1["wastage_value"])), (D(600), D(6)), "consumed 600, wastage 6 (1 percent)")
c.eq((w.qty(bulk["id"]), w.qty(pack["id"])), (D(40), D(40)), "bulk 40, pack 40")
val = {v["product_code"]: v for v in w.valuation() if v["row_type"] == "ITEM"}
c.eq(D(val[pack["code"]]["value"]), D(594), "the pack arrives at the carried cost (594)")
c.eq(D(val[pack["code"]]["rate"]), D("14.85"), "unit cost 14.85")
c.eq(D(val[bulk["code"]]["value"]), D(2400), "bulk valued at 40 x 60")
js = entries(w, r1["repack_number"])
c.eq(len(js), 1, "one wastage journal")
if js:
    net = by_purpose(w, js[0])
    c.eq((net.get("INVENTORY_ADJUSTMENT"), net.get("INVENTORY")), (D(6), D(-6)), "wastage Dr adjustment / Cr inventory 6")
c.eq(w.inventory_account(), books0 - D(6), "books fall by the wastage only")
# without wastage: the books do not move
books1 = w.inventory_account()
st, b = repack("10", "40", "0")
c.eq(st, 201, "repack without wastage posted")
r2 = data(b)
c.eq(w.inventory_account(), books1, "no wastage, books do not move")
c.eq(len(entries(w, r2["repack_number"])), 0, "no journal without wastage")
# cancel reverses everything
st, b = w.admin.post(f"{RP}/{r1['id']}/cancel", {"reason": "mistake"})
c.eq(st, 200, "cancel accepted")
c.eq((w.qty(bulk["id"]), w.qty(pack["id"])), (D(40), D(40)), "cancel puts 10 bulk back and takes 40 packs away")
c.eq(w.inventory_account(), books1 + D(6), "wastage journal reversed")
c.refused(w.admin.post(f"{RP}/{r1['id']}/cancel", {"reason": "again"}), 422, "already cancelled", "cancel twice")
# a repack missing one side is refused
st, b = w.admin.post(RP, {"repack_date": w.today, "branch_id": w.branch_id, "warehouse_id": wh["id"],
                          "lines": [{"kind": "CONSUME", "product_id": bulk["id"], "quantity": "1"}]})
c.eq(st, 422, "no produce line refused")
st, b = w.admin.post(RP, {"repack_date": w.today, "branch_id": w.branch_id, "warehouse_id": wh["id"],
                          "lines": [{"kind": "CONSUME", "product_id": bulk["id"], "quantity": "9999"},
                                    {"kind": "PRODUCE", "product_id": pack["id"], "quantity": "1"}]})
c.ok(st in (409, 422), "consuming more than held is refused", (st, message(b)))
c.done()
