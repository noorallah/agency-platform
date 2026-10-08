"""D-STK-40 (was D-STK-19): a serial follows its goods through both transfers, and opening stock types its units.

Opening stock of a serial-tracked product now carries serial numbers on its line: posting creates the units, a line
that names some but not one per unit is refused, and a line that names none still posts as a quantity (decided
2026-10-08: stores that took opening stock before this could be typed are already in that state).
The units then travel: a one-step transfer and a transfer document each name them, and a unit that arrived at the
other warehouse can be dispatched from there -- the refusal "not in the warehouse this line ships from" was the defect.
"""
from _inv import *
from _flow import *

c = Check("d_stk_19")
w = World()
a = w.warehouse("A")
b = w.warehouse("B")
S = "/api/v1/batch-serial/serials"
T = f"{INV}/stock-transfers"
p = w.product(goods_type="ELECTRONICS")
nums = [f"O{i}{suffix(4)}" for i in range(6)]


def opening(serials: list[str] | None, qty: str, ref: str) -> tuple[int, Any, int]:
    """Create and post one opening stock document; return create status, body and post status."""
    line: dict[str, Any] = {"product_id": p["id"], "quantity": qty, "unit_cost": "10"}
    if serials is not None:
        line["serial_numbers"] = serials
    st, body = w.admin.post(f"{INV}/opening-stock", {"branch_id": w.branch_id, "warehouse_id": a["id"], "reference_number": ref,
                                                    "posting_date": w.today, "lines": [line]})
    if st != 201:
        return st, body, 0
    return st, body, w.admin.post(f"{INV}/opening-stock/{data(body)['id']}/post", {})[0]


def units() -> dict[str, dict]:
    return {x["serial_number"]: x for x in all_rows(w.admin, f"{S}?product_id={p['id']}")}


# ---- opening stock -------------------------------------------------------
st, body, posted = opening(nums[:2], "6", f"SP{w.tag}")
c.eq((st, posted), (201, 422), "6 units with 2 serials saves as a draft and is refused at posting")
c.eq(w.qty(p["id"]), D(0), "and nothing was stocked")
draft = data(body)
c.eq(draft["lines"][0].get("serial_numbers"), nums[:2], "the draft gives back what it typed")
c.eq(draft["lines"][0].get("serial_tracked"), True, "and says the product is serial-tracked")
st, body = w.admin.put(f"{INV}/opening-stock/{draft['id']}", {"branch_id": w.branch_id, "warehouse_id": a["id"], "reference_number": f"SP{w.tag}",
                                                             "posting_date": w.today,
                                                             "lines": [{"product_id": p["id"], "quantity": "6", "unit_cost": "10", "serial_numbers": nums}]})
c.eq(st, 200, "the draft is rewritten with all six: " + message(body)[:80])
st, body = w.admin.post(f"{INV}/opening-stock/{draft['id']}/post", {})
c.eq(st, 200, "and posts: " + message(body)[:80])
rows = units()
c.eq(sorted(rows), sorted(nums), "posting created the six units")
c.eq({(x["status"], x["warehouse_id"]) for x in rows.values()}, {("AVAILABLE", a["id"])}, "AVAILABLE in the document's warehouse")
st, body = w.admin.get(f"{S}/{rows[nums[0]]['id']}/trail")
c.ok(st == 200 and [e["document_type"] for e in data(body).get("events", [])] == ["OPENING_STOCK"], "the unit's trail starts on the opening stock", (st, str(data(body))[:120]))
other = w.product(goods_type="ELECTRONICS")
st, body = w.admin.post(f"{INV}/opening-stock", {"branch_id": w.branch_id, "warehouse_id": a["id"], "reference_number": f"SD{w.tag}", "posting_date": w.today,
                                                "lines": [{"product_id": other["id"], "quantity": "1", "unit_cost": "10", "serial_numbers": [nums[0].lower()]}]})
c.eq(st, 422, "a number the firm already gave a unit is refused, whatever its case: " + message(body)[:70])

# ---- the one-step transfer ----------------------------------------------
move = {"branch_id": w.branch_id, "from_warehouse_id": a["id"], "to_warehouse_id": b["id"], "product_id": p["id"], "quantity": "2", "transaction_date": w.today}
st, body = w.admin.post(f"{INV}/transfers", move)
c.eq(st, 422, "a transfer of serial-tracked goods naming no units is refused: " + message(body)[:80])
st, body = w.admin.post(f"{INV}/transfers", {**move, "serial_ids": [rows[nums[0]]["id"]]})
c.eq(st, 422, "and so is one unit named for two: " + message(body)[:80])
c.eq(w.qty(p["id"], a["id"]), D(6), "nothing moved")
st, body = w.admin.post(f"{INV}/transfers", {**move, "serial_ids": [rows[nums[0]]["id"], rows[nums[1]]["id"]]})
c.eq(st, 201, "with both named it moves: " + message(body)[:80])
rows = units()
c.eq({rows[n]["warehouse_id"] for n in nums[:2]}, {b["id"]}, "and the two units are in the other warehouse")
c.eq((w.qty(p["id"], a["id"]), w.qty(p["id"], b["id"])), (D(4), D(2)), "stock 4 and 2")
st, body = w.admin.post(f"{INV}/transfers", {**move, "quantity": "1", "serial_ids": [rows[nums[0]]["id"]]})
c.eq(st, 422, "a unit that already left cannot leave the source again: " + message(body)[:80])

# ---- the transfer document ----------------------------------------------
ids = [rows[n]["id"] for n in nums[2:6]]
doc = {"transfer_date": w.today, "from_warehouse_id": a["id"], "to_warehouse_id": b["id"], "lines": [{"product_id": p["id"], "quantity": "4", "serial_ids": ids[:1]}]}
st, body = w.admin.post(T, doc)
c.eq(st, 201, "a draft may name fewer units than it sends: " + message(body)[:60])
tid = data(body)["id"]
c.eq([s["serial_number"] for s in data(body)["lines"][0].get("serials", [])], [nums[2]], "and shows the one it named")
st, body = w.admin.post(f"{T}/{tid}/dispatch", {})
c.eq(st, 422, "dispatch is refused until there is one per unit: " + message(body)[:90])
doc["lines"][0]["serial_ids"] = ids
st, body = w.admin.put(f"{T}/{tid}", doc)
c.eq(st, 200, "the draft is rewritten with all four")
st, body = w.admin.post(f"{T}/{tid}/dispatch", {})
c.eq(st, 200, "and dispatches: " + message(body)[:80])
c.eq({units()[n]["status"] for n in nums[2:6]}, {"IN_TRANSIT"}, "its units are IN_TRANSIT")
st, body = w.admin.post(f"{T}/{tid}/receive", {"lines": [{"line_number": 1, "received_quantity": "3", "damaged_quantity": "1"}]})
c.eq(st, 422, "a short, damaged receipt that does not say which units is refused: " + message(body)[:90])
st, body = w.admin.post(f"{T}/{tid}/receive", {"lines": [{"line_number": 1, "received_quantity": "3", "damaged_quantity": "1",
                                                          "short_serial_ids": [ids[3]], "damaged_serial_ids": [ids[2]]}]})
c.eq(st, 200, "naming them, it is received: " + message(body)[:80])
rows = units()
c.eq([(rows[n]["status"], rows[n]["warehouse_id"]) for n in nums[2:6]],
     [("AVAILABLE", b["id"]), ("AVAILABLE", b["id"]), ("DAMAGED", b["id"]), ("LOST", a["id"])],
     "two good units and the damaged one are at the destination; the missing one is LOST")
c.eq((w.qty(p["id"], a["id"]), w.qty(p["id"], b["id"])), (D(0), D(4)), "stock: none at the source, 4 sellable at the destination")

# ---- the point of it all: what arrived can be shipped from where it is ----
s = sell_and_dispatch(w, b["id"], p["id"], 2, serial_ids=[rows[nums[0]]["id"], rows[nums[2]]["id"]])
c.eq(s["dispatch"][0], 200, "a unit moved in one step and a unit moved on a document both dispatch from the destination: " + message(s["dispatch"][1])[:90])
s = sell_and_dispatch(w, b["id"], p["id"], 1, serial_ids=[rows[nums[4]]["id"]])
c.ok(s.get("note_create", (0,))[0] == 422 or s.get("dispatch", (0,))[0] == 422, "the damaged unit cannot be dispatched",
     {k: (v[0] if isinstance(v, tuple) else "") for k, v in s.items()})

# ---- a cancelled transfer gives its units back ---------------------------
q = w.product(goods_type="ELECTRONICS")
qn = [f"C{i}{suffix(4)}" for i in range(2)]
r = receive(w, a["id"], q["id"], 2, serials=qn)
c.eq(r["status"][0], 200, "two more units received")
qrows = {x["serial_number"]: x for x in all_rows(w.admin, f"{S}?product_id={q['id']}")}
st, body = w.admin.post(T, {"transfer_date": w.today, "from_warehouse_id": a["id"], "to_warehouse_id": b["id"],
                            "lines": [{"product_id": q["id"], "quantity": "2", "serial_ids": [qrows[n]["id"] for n in qn]}]})
tid = data(body)["id"]
c.eq(w.admin.post(f"{T}/{tid}/dispatch", {})[0], 200, "dispatched")
c.eq(w.admin.post(f"{T}/{tid}/cancel", {"reason": "lorry broke down"})[0], 200, "and cancelled")
qrows = {x["serial_number"]: x for x in all_rows(w.admin, f"{S}?product_id={q['id']}")}
c.eq({(x["status"], x["warehouse_id"]) for x in qrows.values()}, {("AVAILABLE", a["id"])}, "its units are AVAILABLE at the source again")
c.eq(w.qty(q["id"], a["id"]), D(2), "with their stock")

# ---- a line with no serials still posts as a quantity --------------------
plain = w.product(goods_type="ELECTRONICS")
st, body = w.admin.post(f"{INV}/opening-stock", {"branch_id": w.branch_id, "warehouse_id": a["id"], "reference_number": f"SN{w.tag}", "posting_date": w.today,
                                                "lines": [{"product_id": plain["id"], "quantity": "4", "unit_cost": "10"}]})
st2 = w.admin.post(f"{INV}/opening-stock/{data(body)['id']}/post", {})[0] if st == 201 else 0
c.eq((st, st2), (201, 200), "opening stock naming no serial at all posts as a quantity (decided 2026-10-08)")
c.done()
