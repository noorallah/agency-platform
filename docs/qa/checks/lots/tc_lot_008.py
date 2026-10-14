"""TC-LOT-008: a write-off or transfer that names no lot; adjustments up."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _lot import *  # noqa: F401,F403

c0 = Check("tc_lot_008")
api = lot_admin(); c = Ctx(api)
p = c.product("B")
lots = two_lots(c, p, 10, 10)
w2 = c.second_warehouse()


def held(wh):
    """Return {batch_number: row} for one warehouse."""
    rows = rows_of(api.get(f"{INV}/reports/stock-valuation/lots?product_id={p['id']}&warehouse_id={wh['id']}"))
    return {(r["batch_number"] or r["lot_reference"]): r for r in rows}, rows


# (1) write off 2 with no batch: leaves the first lot (nearest expiry, LOTA) at its cost.
s, body = c.write_off(p, "2")
c0.eq(s, 201, f"write-off 2 accepted ({message(body)})")
m, _ = held(c.warehouse)
c0.eq((D(m["LOTA"]["quantity"]), D(m["LOTB"]["quantity"])), (D(8), D(10)), "the 2 left LOTA, nearest expiry first")
c0.eq(D(m["LOTA"]["rate"]), D(40), "LOTA's cost stands")
# (2) transfer 3 without a batch: from the first lot that holds all 3, arriving at the same value.
s, body = c.transfer(p, "3", w2)
c0.eq(s, 201, f"transfer 3 accepted ({message(body)})")
m, _ = held(c.warehouse)
c0.eq(D(m["LOTA"]["quantity"]), D(5), "the 3 left LOTA (the first lot holding all 3)")
d, drows = held(w2)
c0.eq((len(drows), sum(D(r["quantity"]) for r in drows), [D(r["rate"]) for r in drows], sum(D(r["value"]) for r in drows)),
      (1, D(3), [D(40)], D(120)), "3 arrived in the second warehouse at the lot's cost, value 120")
# (3) 12 > LOTA 5 and > LOTB 10 individually? LOTB holds 10 -> 12 is above each, below both together (15).
s, body = c.write_off(p, "12")
text = message(body)
c0.ok(s == 422 and "LOTA 5" in text and "LOTB 10" in text,
      "12 is refused naming both lots", (s, text[:250]))
# (4) adjust up 4, no lot, cost 45: a new lot (source Adjustment) at 45.
before = {r["lot_reference"] for r in c.lots(p)}
s, body = c.adjust(p, "4", unit_cost="45.00")
c0.eq(s, 201, f"adjustment up accepted ({message(body)})")
new = [r for r in c.lots(p) if r["lot_reference"] not in before and D(r["quantity"]) == 4]
c0.eq(len(new), 1, "a new lot of 4 appeared")
if new:
    c0.eq(D(new[0]["rate"]), D(45), "at 45.00")
    nb = next((b for b in c.batches(p) if b["batch_number"] == new[0]["lot_reference"]), None)
    nt = data(trail(api, nb["id"])[1]) if nb else {}
    c0.eq(nt.get("source_type"), "ADJUSTMENT", "source is Adjustment")
# (5) naming an existing lot and a cost is refused.
s, body = c.adjust(p, "4", batch_id=lots["a"]["id"], unit_cost="45.00")
c0.ok(s == 422 and "cost" in message(body).lower(), "a cost on a named lot is refused", (s, message(body)))
c0.done()
