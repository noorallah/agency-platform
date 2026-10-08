"""TC-STOCK-012: a kit is assembled, disassembled, sold as itself, dispatched by assembling."""
from _inv import *
from _flow import *

c = Check("tc_stock_012")
w = World()
wh = w.warehouse()
det, oth = w.product("DET"), w.product("OTH")
kit = w.product("KIT", product_type="BUNDLE")
w.stock_in(wh["id"], det["id"], 100, 60)
w.stock_in(wh["id"], oth["id"], 100, 20)
PR = "/api/v1/products"
st, b = w.admin.put(f"{PR}/{kit['id']}/components", {"components": [
    {"component_product_id": det["id"], "quantity": "2"}, {"component_product_id": oth["id"], "quantity": "1"}]})
c.eq(st, 200, "components saved")
body = {"branch_id": w.branch_id, "warehouse_id": wh["id"], "quantity": "5"}
books0 = w.inventory_account()
st, b = w.admin.post(f"{PR}/{kit['id']}/assemble", body)
c.eq(st, 200, "assemble 5")
c.eq((w.qty(det["id"]), w.qty(oth["id"]), w.qty(kit["id"])), (D(90), D(95), D(5)), "10 DET and 5 OTH consumed, 5 kits made")
val = {v["product_code"]: v for v in w.valuation() if v["row_type"] == "ITEM"}
c.eq(D(val[kit["code"]]["value"]), D(700), "the kit carries the components cost (10x60 + 5x20 = 700)")
c.eq(D(val[kit["code"]]["rate"]), D(140), "140 per kit")
c.eq(w.inventory_account(), books0, "assembling moves nothing in the books")
st, b = w.admin.post(f"{PR}/{kit['id']}/disassemble", {**body, "quantity": "1"})
c.eq(st, 200, "disassemble 1")
c.eq((w.qty(det["id"]), w.qty(oth["id"]), w.qty(kit["id"])), (D(92), D(96), D(4)), "components back, 4 kits")
# too many kits to assemble
c.ok(w.admin.post(f"{PR}/{kit['id']}/assemble", {**body, "quantity": "100"})[0] == 422, "assembling beyond the components is refused")
c.ok(w.admin.post(f"{PR}/{kit['id']}/disassemble", {**body, "quantity": "100"})[0] == 422, "disassembling more kits than held is refused")
# kit inside a kit
kit2 = w.product("KIT2", product_type="BUNDLE")
st, b = w.admin.put(f"{PR}/{kit2['id']}/components", {"components": [{"component_product_id": kit["id"], "quantity": "1"}]})
c.refused((st, b), 422, "not a component of another kit", "a kit inside a kit")
# dispatch 8 with only 4 assembled
s = sell_and_dispatch(w, wh["id"], kit["id"], 8)
c.eq(s.get("approve", (0,))[0], 200, "order for 8 kits approves")
c.eq(s.get("dispatch", (0, ""))[0], 200, "dispatch of 8 assembles the shortfall of 4")
c.eq(w.qty(kit["id"]), D(-4 + 4) if False else D(0), "all 8 kits left")
c.eq((w.qty(det["id"]), w.qty(oth["id"])), (D(92 - 8), D(96 - 4)), "4 more kits cost 8 DET and 4 OTH")
disp = [x for x in w.ledger(kit["id"]) if x["transaction_type"] == "DISPATCH"]
c.eq([D(x["quantity"]) for x in disp], [D(8)], "DISPATCH of 8 kits")
c.done()
