"""Probe (round 4): broken kits put a batch-tracked part back into a batch, never into stock with none (D-STK-53).

The part goes back into the batch the kit's last assembly here drew it from; a kit never assembled in the
warehouse says so and takes the batch the caller names."""
from _r3 import *
from _flow import receive

c = Check("p_kit_break_batch")
w = World()
wh = w.warehouse()["id"]
PR = "/api/v1/products"
med = w.product(goods_type="MEDICINE")
a, b = f"BA{w.tag}", f"BB{w.tag}"
receive(w, wh, med["id"], 4, batch=a, mfg=iso(w, -30), expiry=iso(w, 100))
receive(w, wh, med["id"], 16, batch=b, mfg=iso(w, -10), expiry=iso(w, 300))
where = {"branch_id": w.branch_id, "warehouse_id": wh}
parts = {"components": [{"component_product_id": med["id"], "quantity": "5"}]}

kit = w.product("KIT", product_type="BUNDLE")
c.eq(w.admin.put(f"{PR}/{kit['id']}/components", parts)[0], 200, "the kit takes five of the medicine")
st, body = w.admin.post(f"{PR}/{kit['id']}/assemble", {**where, "quantity": "1"})
c.eq(st, 200, "one kit assembled: " + message(body))
c.eq(by_batch(w, med["id"]), {a: D(0), b: D(15)}, "four of the first batch and one of the second went into it")
st, body = w.admin.post(f"{PR}/{kit['id']}/disassemble", {**where, "quantity": "1"})
c.eq(st, 200, "the kit is broken naming no batch: " + message(body))
held = by_batch(w, med["id"])
c.ok(None not in held, "nothing came back with no batch", held)
c.eq(held, {a: D(0), b: D(20)}, "the five went back into the batch the assembly last drew from")
c.eq(w.qty(kit["id"], wh), D(0), "and no kit is left")

# A kit brought in as stock was never assembled here, so nothing says where its part came from.
other = w.product("KIT", product_type="BUNDLE")
c.eq(w.admin.put(f"{PR}/{other['id']}/components", parts)[0], 200, "a second kit of the same part")
w.stock_in(wh, other["id"], 1)
st, body = w.admin.post(f"{PR}/{other['id']}/disassemble", {**where, "quantity": "1"})
c.refused((st, body), 422, "Name the batch", "a kit never assembled here is not broken into a part with no batch")
c.eq((w.qty(other["id"], wh), by_batch(w, med["id"])), (D(1), {a: D(0), b: D(20)}), "and nothing moved")
st, body = w.admin.post(f"{PR}/{other['id']}/disassemble", {**where, "quantity": "1", "part_batches": [{"product_id": med["id"], "batch_number": a}]})
c.eq(st, 200, "naming the batch breaks it: " + message(body))
c.eq(by_batch(w, med["id"]), {a: D(5), b: D(20)}, "the five went into the batch named")
c.done()
