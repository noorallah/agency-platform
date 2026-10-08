"""Probe (round 7): a note never assembles a kit that is itself kept in batches (D-STK-53).

A kit under a medicine category, two assembled into a named batch, parts on the shelf for more. A note for three is
refused at dispatch and no part is taken; once the third is assembled into the batch by name the same note ships.
The same kit not kept in batches has what it lacks assembled behind the note."""
from _r3 import *

c = Check("p_kit_batch_kit_dispatch")
w = World()
wh = w.warehouse()["id"]
PR = "/api/v1/products"
where = {"branch_id": w.branch_id, "warehouse_id": wh}

part = w.product()
w.stock_in(wh, part["id"], 20)
kit = w.product("KIT", product_type="BUNDLE", goods_type="MEDICINE")
c.ok(kit.get("track_batch") is True, "a kit under a medicine category is kept in batches", kit.get("track_batch"))
c.eq(w.admin.put(f"{PR}/{kit['id']}/components", {"components": [{"component_product_id": part["id"], "quantity": "2"}]})[0], 200,
     "it takes two of a plain part")
a = f"KD{w.tag}"
st, body = w.admin.post(f"{PR}/{kit['id']}/assemble", {**where, "quantity": "2", "batch_number": a, "expiry_date": iso(w, 120)})
c.eq(st, 200, "two assembled into a named batch: " + message(body))
c.eq((by_batch(w, kit["id"]), w.qty(part["id"], wh)), ({a: D(2)}, D(16)), "two kits in the batch, sixteen parts left")


def held():
    """The kit per batch, leaving out a row that holds nothing (an order's reservation stands in one)."""
    return {k: v for k, v in by_batch(w, kit["id"]).items() if v != D(0) or k is not None}


so = order(w, wh, kit["id"], 3)
line = {"sales_order_line_id": so["lines"][0]["id"], "line_number": 1, "current_delivery_quantity": "3", "warehouse_id": wh}
made = w.admin.post("/api/v1/delivery-notes", {"sales_order_id": so["id"], "delivery_date": w.today, "lines": [line]})
c.ok(made[0] in (200, 201), "a note for three is raised with two assembled", (made[0], message(made[1])[:200]))
note = data(made[1])["id"]
c.eq(w.admin.post(f"/api/v1/delivery-notes/{note}/approve", {})[0], 200, "and approved")
st, body = w.admin.post(f"/api/v1/delivery-notes/{note}/dispatch", {})
c.refused((st, body), 422, "stock", "dispatched, it is not assembled behind the note")
c.eq((held(), w.qty(part["id"], wh)), ({a: D(2)}, D(16)), "no kit left and no part was taken")

st, body = w.admin.post(f"{PR}/{kit['id']}/assemble", {**where, "quantity": "1", "batch_number": a})
c.eq(st, 200, "somebody assembles the third into the batch by name: " + message(body))
c.eq((held(), w.qty(part["id"], wh)), ({a: D(3)}, D(14)), "three kits in the batch, two more parts went")
st, body = w.admin.post(f"/api/v1/delivery-notes/{note}/dispatch", {})
c.eq(st, 200, "the same note now ships: " + message(body)[:240])
c.eq((held(), w.qty(part["id"], wh)), ({a: D(0)}, D(14)), "the batch is empty and no part went behind the note")
c.eq([D(r.get("reserved_quantity", 0)) for r in w.rows(kit["id"])].count(D(0)), len(w.rows(kit["id"])), "nothing of the kit is left reserved")

# The same kit not kept in batches: the note assembles what it lacks.
plain_kit = w.product("KIT", product_type="BUNDLE")
c.eq(w.admin.put(f"{PR}/{plain_kit['id']}/components", {"components": [{"component_product_id": part["id"], "quantity": "2"}]})[0], 200,
     "a plain kit of the same part")
so3 = order(w, wh, plain_kit["id"], 3)
st, said = ship(w, so3, wh, 3)
c.eq(st, 200, "a note for three plain kits, none assembled, ships: " + said[:240])
c.eq((w.qty(plain_kit["id"], wh), w.qty(part["id"], wh)), (D(0), D(8)), "the kits left and six parts went into them")
c.done()
