"""Probe (round 6): the component list says which parts are kept in batches, and a kit that is itself kept in batches (D-UI-85).

The screen asks for a batch only where the server will: ``track_batch`` on a component follows the part as it
is now, not as it was when the kit was saved. A kit kept in batches names its batch when it is assembled."""
from _r3 import *
from _flow import receive

c = Check("p_kit_batch_tracked_kit")
w = World()
wh = w.warehouse()["id"]
PR = "/api/v1/products"
where = {"branch_id": w.branch_id, "warehouse_id": wh}


def flags(kit_id):
    """Component product id -> track_batch, as the kit dialog reads it."""
    return {x["component_product_id"]: x["track_batch"] for x in must(w.admin.get(f"{PR}/{kit_id}/components"), "components")}


# The flag follows the part.
plain = w.product()
med = w.product(goods_type="MEDICINE")
kit = w.product("KIT", product_type="BUNDLE")
st, body = w.admin.put(f"{PR}/{kit['id']}/components", {"components": [
    {"component_product_id": plain["id"], "quantity": "1"},
    {"component_product_id": med["id"], "quantity": "2"},
]})
c.eq(st, 200, "a kit of a plain part and a medicine: " + message(body))
c.eq({x["component_product_id"]: x["track_batch"] for x in data(body)}, {plain["id"]: False, med["id"]: True},
     "the save answers which part is kept in batches")
c.eq(flags(kit["id"]), {plain["id"]: False, med["id"]: True}, "and so does the list read afterwards")
st, body = w.update_product(plain, track_batch=True)
c.eq(st, 200, "the plain part, holding nothing, is switched to batches: " + message(body))
c.eq(flags(kit["id"]), {plain["id"]: True, med["id"]: True}, "the list now says both parts are kept in batches")
st, body = w.update_product(plain, track_batch=False)
c.eq(st, 200, "and switched back: " + message(body))
c.eq(flags(kit["id"]), {plain["id"]: False, med["id"]: True}, "the list follows it")

# A kit that is itself kept in batches.
part = w.product()
w.stock_in(wh, part["id"], 10)
bkit = w.product("KIT", product_type="BUNDLE", goods_type="MEDICINE")
c.ok(bkit.get("track_batch") is True, "a kit under a medicine category is kept in batches", bkit.get("track_batch"))
c.eq(w.admin.put(f"{PR}/{bkit['id']}/components", {"components": [{"component_product_id": part["id"], "quantity": "2"}]})[0], 200,
     "it takes two of a plain part")
st, body = w.admin.post(f"{PR}/{bkit['id']}/assemble", {**where, "quantity": "1"})
c.refused((st, body), 422, "batch", "assembled naming no batch")
c.eq((w.qty(part["id"], wh), by_batch(w, bkit["id"])), (D(10), {}), "and nothing moved")
a, b = f"KX{w.tag}", f"KY{w.tag}"
st, body = w.admin.post(f"{PR}/{bkit['id']}/assemble", {**where, "quantity": "2", "batch_number": a,
                                                         "manufacturing_date": iso(w, -1), "expiry_date": iso(w, 200)})
c.eq(st, 200, "two assembled into a named batch: " + message(body))
st, body = w.admin.post(f"{PR}/{bkit['id']}/assemble", {**where, "quantity": "1", "batch_number": b, "expiry_date": iso(w, 90)})
c.eq(st, 200, "one more into a second batch that expires sooner, as the dialog sends it (no manufacturing date): " + message(body))
c.eq((by_batch(w, bkit["id"]), w.qty(part["id"], wh)), ({a: D(2), b: D(1)}, D(4)), "the kits stand in their batches and six parts went")
# A batch already there keeps its own date, as on a goods receipt: the date typed beside its number is not taken.
st, body = w.admin.post(f"{PR}/{bkit['id']}/assemble", {**where, "quantity": "1", "batch_number": a, "expiry_date": iso(w, 5)})
c.eq(st, 200, "the first batch named again beside another expiry date: " + message(body))
c.eq((by_batch(w, bkit["id"]), w.qty(part["id"], wh)), ({a: D(3), b: D(1)}, D(2)), "the kit joins that batch")
dates = {x["batch_number"]: x["expiry_date"] for x in all_rows(w.admin, f"/api/v1/batch-serial/batches?product_id={bkit['id']}")}
c.eq(dates, {a: iso(w, 200), b: iso(w, 90)}, "and each batch keeps the date it was made with")

# Breaking it takes the kits out of their batches, soonest expiry first, never below nought.
st, body = w.admin.post(f"{PR}/{bkit['id']}/disassemble", {**where, "quantity": "2"})
c.eq(st, 200, "two broken: " + message(body))
c.eq((by_batch(w, bkit["id"]), w.qty(part["id"], wh)), ({a: D(2), b: D(0)}, D(6)), "the batch expiring first went, then one of the other; four parts came back")
c.refused(w.admin.post(f"{PR}/{bkit['id']}/disassemble", {**where, "quantity": "3"}), 422, bkit["code"], "three more broken with two held")
c.eq((by_batch(w, bkit["id"]), w.qty(part["id"], wh)), ({a: D(2), b: D(0)}, D(6)), "and nothing moved")
c.done()
