"""Probe (round 3): a kit whose part is held in batches is assembled earliest expiry first; serial-tracked goods are refused on a repack and in a kit (D-STK-51, D-STK-52)."""
from _r3 import *
from _flow import receive, sell_and_dispatch

c = Check("p_kit_tracked_parts")
w = World()
wh = w.warehouse()["id"]
PR = "/api/v1/products"
med = w.product(goods_type="MEDICINE")
a, b = f"KA{w.tag}", f"KB{w.tag}"
receive(w, wh, med["id"], 4, batch=a, mfg=iso(w, -30), expiry=iso(w, 100))
receive(w, wh, med["id"], 16, batch=b, mfg=iso(w, -10), expiry=iso(w, 300))
kit = w.product("KIT", product_type="BUNDLE")
st, body = w.admin.put(f"{PR}/{kit['id']}/components", {"components": [{"component_product_id": med["id"], "quantity": "5"}]})
c.eq(st, 200, "a batch-tracked part is saved on a kit: " + message(body))
where = {"branch_id": w.branch_id, "warehouse_id": wh}
st, body = w.admin.post(f"{PR}/{kit['id']}/assemble", {**where, "quantity": "1"})
c.eq(st, 200, "one kit of five is assembled from two batches: " + message(body))
c.eq(by_batch(w, med["id"]), {a: D(0), b: D(15)}, "the four expiring first went, then one of the later batch")
c.eq(w.qty(kit["id"], wh), D(1), "one kit is held")
st, body = w.admin.post(f"{PR}/{kit['id']}/assemble", {**where, "quantity": "4"})
c.refused((st, body), 422, med["code"], "four more kits, twenty needed and fifteen held")
c.eq(by_batch(w, med["id"]), {a: D(0), b: D(15)}, "and nothing moved")
s = sell_and_dispatch(w, wh, kit["id"], 3)
dispatched = s.get("dispatch", (0, ""))
c.eq(dispatched[0], 200, "a note for three kits assembles the two it lacks: " + message(dispatched[1]))
c.eq((w.qty(kit["id"], wh), by_batch(w, med["id"])), (D(0), {a: D(0), b: D(5)}), "the kits left and ten more of the later batch went into them")

# Serial-tracked goods: a repack names no units, so it is refused rather than moving the stock under them.
ele = w.product(goods_type="ELECTRONICS")
plain = w.product()
w.stock_in(wh, plain["id"], 5)
receive(w, wh, ele["id"], 3, serials=[f"K{i}{suffix(4)}" for i in range(3)])
head = {"repack_date": w.today, **where}
for label, lines in (
    ("consumed", [{"kind": "CONSUME", "product_id": ele["id"], "quantity": "1"}, {"kind": "PRODUCE", "product_id": plain["id"], "quantity": "1"}]),
    ("produced", [{"kind": "CONSUME", "product_id": plain["id"], "quantity": "1"}, {"kind": "PRODUCE", "product_id": ele["id"], "quantity": "1"}]),
):
    c.refused(w.admin.post(f"{INV}/repacks", {**head, "lines": lines}), 422, "serial number", f"a serial-tracked product {label} by a repack")
c.eq((w.qty(ele["id"], wh), w.qty(plain["id"], wh)), (D(3), D(5)), "no stock moved")
c.eq([x["status"] for x in units(w, ele["id"]).values()], ["AVAILABLE"] * 3, "three units, three held")
kit2 = w.product("KIT", product_type="BUNDLE")
c.refused(
    w.admin.put(f"{PR}/{kit2['id']}/components", {"components": [{"component_product_id": ele["id"], "quantity": "1"}]}),
    422, "serial number", "a serial-tracked part on a kit",
)
c.done()
