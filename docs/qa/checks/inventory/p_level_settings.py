"""Probe (round 12): stock levels as settings.

What a stock row's levels accept by every way they can be written (the
row itself, a row made by hand, an opening-stock line), who may write
them, what a figure too large for the column answers, and whether a row
that was removed can still be edited.
"""
from _inv import *

c = Check("p_level_settings")
w = World()
store = client("store")
sales = client("sales")
viewer = client("viewer")
other = client("other_admin")
a = w.warehouse()
p = w.product()
w.stock_in(a["id"], p["id"], 10)
row = w.rows(p["id"])[0]
key = {"branch_id": w.branch_id, "warehouse_id": a["id"], "product_id": p["id"]}
sane = {**key, "minimum_level": "2", "maximum_level": "50", "reorder_level": "5", "safety_stock": "1"}
URL = f"{INV}/{row['id']}"


def levels(product_id: str = p["id"]) -> dict:
    """The levels the product's row holds now."""
    held = w.rows(product_id)[0]
    return {k: (None if held[k] is None else D(held[k])) for k in ("minimum_level", "maximum_level", "reorder_level", "safety_stock")}


def refused(label: str, answer: tuple[int, object]) -> None:
    """Must be a 422."""
    c.ok(answer[0] == 422, f"{label} is refused", (answer[0], message(answer[1])))


c.eq(w.admin.put(URL, sane)[0], 200, "sane levels save")
before = levels()

# ---- who may write them ---------------------------------------------------
c.eq(store.put(URL, sane)[0], 200, "the warehouse role may set levels")
c.eq(viewer.put(URL, {**sane, "reorder_level": "9"})[0], 403, "a viewer may not")
c.eq(sales.put(URL, {**sane, "reorder_level": "9"})[0], 403, "nor the sales role")
c.ok(other.put(URL, {**sane, "reorder_level": "9"})[0] in (403, 404), "nor an administrator of another firm")
c.eq(viewer.post(INV, {**key, "product_id": w.product("V")["id"]})[0], 403, "a viewer may not make a stock row")
c.eq(levels(), before, "the refused writes changed nothing")

# ---- what a level accepts -------------------------------------------------
for label, patch in (
    ("a level of text", {"reorder_level": "plenty"}),
    ("a level of spaces", {"reorder_level": "   "}),
    ("a level that is not a number", {"reorder_level": "NaN"}),
    ("an endless level", {"maximum_level": "Infinity"}),
    ("a level too large for the column", {"maximum_level": "999999999999999999"}),
    ("a level of nineteen digits", {"maximum_level": "1234567890123456789"}),
    ("a negative minimum", {"minimum_level": "-0.0001"}),
    ("a reorder level above the maximum", {"reorder_level": "50.0001"}),
    ("a status nobody declared", {"status": "ASLEEP"}),
    ("a field nobody declared", {"lead_time_days": 4}),
    ("a quantity written as a level", {"current_quantity": "500"}),
):
    answer = w.admin.put(URL, {**sane, **patch})
    c.ok(answer[0] == 422, f"{label} is refused", (answer[0], message(answer[1])))
c.eq(levels(), before, "none of them changed the levels")
c.eq(w.qty(p["id"], a["id"]), D(10), "nor the quantity")

# the largest figure the column holds is taken, not a 500
st, b = w.admin.put(URL, {**sane, "maximum_level": "99999999999999"})
c.eq(st, 200, "the largest figure the column holds is saved")
c.eq(w.admin.put(URL, sane)[0], 200, "and put back")

# leaving a level out clears it: the editor sends every level it holds
st, b = w.admin.put(URL, {**key, "minimum_level": "2"})
c.eq(st, 200, "a save that names one level is taken")
c.eq(levels()["reorder_level"], None, "and the levels it left out are cleared, as the editor's whole-row save means")
c.eq(w.admin.put(URL, sane)[0], 200, "the levels are put back")

# ---- a row made by hand ---------------------------------------------------
q = w.product("H")
refused("a hand-made row with the minimum above the maximum", w.admin.post(INV, {**key, "product_id": q["id"], "minimum_level": "9", "maximum_level": "3"}))
refused("a hand-made row with a level too large for the column", w.admin.post(INV, {**key, "product_id": q["id"], "maximum_level": "999999999999999999"}))
c.eq(len(w.rows(q["id"])), 0, "neither made a row")
st, b = w.admin.post(INV, {**key, "product_id": q["id"], "reorder_level": "4"})
c.eq(st, 201, "a row made by hand with a level is saved")
made = data(b)
c.eq(D(made["current_quantity"]), D(0), "and holds nothing")
c.eq(w.admin.post(INV, {**key, "product_id": q["id"]})[0], 409, "the same place twice is refused")
answer = w.admin.post(INV, {**key, "product_id": "00000000-0000-0000-0000-000000000001"})
c.ok(answer[0] in (404, 422), "a row for a product nobody has is refused", (answer[0], message(answer[1])))

# ---- a row that was removed ----------------------------------------------
c.eq(w.admin.delete(f"{INV}/{made['id']}")[0], 204, "an empty row is removed")
c.eq(w.admin.get(f"{INV}/{made['id']}")[0], 404, "and is gone")
answer = w.admin.put(f"{INV}/{made['id']}", {**key, "product_id": q["id"], "reorder_level": "7"})
c.ok(answer[0] == 404, "its levels cannot be changed once it is removed", (answer[0], message(answer[1])))
c.eq(len(w.rows(q["id"])), 0, "and it did not come back")

# ---- levels typed on an opening-stock line --------------------------------
o = w.product("O")


def opening(ref: str, **line: str) -> tuple[int, object]:
    """Save an opening-stock draft of one line carrying levels."""
    return w.admin.post(f"{INV}/opening-stock", {
        "branch_id": w.branch_id, "warehouse_id": a["id"], "posting_date": w.today, "reference_number": f"{ref}{w.tag}",
        "lines": [{"product_id": o["id"], "quantity": "1", "unit_cost": "10", **line}]})


refused("an opening-stock line with the minimum above the maximum", opening("LA", minimum_level="9", maximum_level="3"))
refused("an opening-stock line with the reorder level above the maximum", opening("LB", reorder_level="9", maximum_level="3"))
refused("an opening-stock line with a negative level", opening("LC", safety_stock="-1"))
refused("an opening-stock line with a level too large for the column", opening("LD", maximum_level="999999999999999999"))
c.eq(len(w.rows(o["id"])), 0, "none of them made a row")

# ---- a figure too large for its column, on every stock write --------------
HUGE = "999999999999999999"
base = {**key, "transaction_date": w.today}
for label, path, body in (
    ("an opening quantity", "opening-stock", {"branch_id": w.branch_id, "warehouse_id": a["id"], "posting_date": w.today, "reference_number": f"HA{w.tag}",
                                              "lines": [{"product_id": o["id"], "quantity": HUGE, "unit_cost": "10"}]}),
    ("an opening cost", "opening-stock", {"branch_id": w.branch_id, "warehouse_id": a["id"], "posting_date": w.today, "reference_number": f"HB{w.tag}",
                                          "lines": [{"product_id": o["id"], "quantity": "1", "unit_cost": HUGE}]}),
    ("an adjustment upwards", "adjustments", {**base, "quantity": HUGE}),
    ("an adjustment downwards", "adjustments", {**base, "quantity": f"-{HUGE}"}),
    ("a write-off", "write-offs", {**base, "quantity": HUGE, "reason": "DAMAGE"}),
    ("a quarantine hold", "quarantine", {**base, "quantity": HUGE, "action": "HOLD"}),
):
    answer = w.admin.post(f"{INV}/{path}", body)
    c.ok(answer[0] == 422, f"{label} too large for its column is refused, not an outage", (answer[0], message(answer[1])))
# a figure that fits each field and overflows only when multiplied is still a plain refusal
import json  # noqa: E402

answer = w.admin.upload(f"{INV}/opening-stock/import", "os.json", b"{}", fields={"format": "json", "payload": json.dumps({
    "branch_id": w.branch_id, "warehouse_id": a["id"], "posting_date": w.today, "reference_number": f"HC{w.tag}",
    "lines": [{"product_id": o["id"], "quantity": "99999999999999", "unit_cost": "999999999999"}]})})
c.ok(answer[0] == 422, "a value that overflows only when multiplied is refused, never an outage", (answer[0], message(answer[1])))
c.eq(w.qty(p["id"], a["id"]), D(10), "the stock is as it was")

# ---- a service is never held as stock -------------------------------------
service = w.product("S", product_type="SERVICE")
sbase = {**base, "product_id": service["id"]}
says = "never held as stock"
c.refused(w.admin.post(INV, {**key, "product_id": service["id"], "reorder_level": "4"}), 422, says, "a stock row made by hand for a service")
c.refused(w.admin.post(f"{INV}/adjustments", {**sbase, "quantity": "5"}), 422, says, "an adjustment that brings a service into stock")
c.refused(store.post(f"{INV}/adjustment-requests", {"kind": "ADJUSTMENT", "adjustment": {**sbase, "quantity": "5"}}), 422, says, "a request to do so")
c.refused(w.admin.post(f"{INV}/opening-stock", {"branch_id": w.branch_id, "warehouse_id": a["id"], "posting_date": w.today, "reference_number": f"SV{w.tag}",
                                                            "lines": [{"product_id": service["id"], "quantity": "3", "unit_cost": "10"}]}), 422, says, "opening stock of a service")
c.refused(w.admin.post(f"{INV}/repacks", {"repack_date": w.today, "branch_id": w.branch_id, "warehouse_id": a["id"], "lines": [
    {"kind": "CONSUME", "product_id": p["id"], "quantity": "1"}, {"kind": "PRODUCE", "product_id": service["id"], "quantity": "1"}]}), 422, says, "a repack that produces a service")
c.eq(len(w.rows(service["id"])), 0, "the service holds no stock row")
c.eq(w.qty(p["id"], a["id"]), D(10), "and nothing was consumed for it")
c.done()
