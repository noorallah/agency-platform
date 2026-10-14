"""TC-LOT-004: the picker groups lots, fills oldest first, shows a dash for an unprinted lot."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _lot import *  # noqa: F401,F403

c0 = Check("tc_lot_004")
api = lot_admin(); c = Ctx(api)
p, q = c.product("B"), c.product("P", batch=False)
lots = two_lots(c, p, 10, 10)                        # LOTA 10 @40 (+180d), LOTB 10 @42 (+365d)
exp_a = today() + timedelta(days=180)
# (1) 5 more with the very same batch, expiry, MRP, prices at a third cost.
c.receive([{"product": p, "qty": 5, "rate": 44, "batch": "LOTA", "expiry": exp_a, "mrp": 150}])
c.receive([{"product": q, "qty": 6, "rate": 30}])
PICK = "/api/v1/batch-serial/batches/availability"


def picker(api2, product, qty, wh=None):
    """Read the picker for a product."""
    return api2.get(f"{PICK}?product_id={product['id']}&warehouse_id={(wh or c.warehouse)['id']}&quantity={qty}")


s, body = picker(api, p, 12)
c0.eq(s, 200, "picker answers")
rows = data(body) if s == 200 else []
c0.eq(len(rows), 3, "three lot rows come back (two LOTA lots and LOTB)")
a_rows = [r for r in rows if r["batch_number"] == "LOTA"]
b_rows = [r for r in rows if r["batch_number"] == "LOTB"]
c0.eq(len(a_rows), 2, "two LOTA lots listed")
if len(a_rows) == 2 and b_rows:
    c0.eq(a_rows[0]["pick_group"], a_rows[1]["pick_group"], "lots that agree share one pick_group")
    c0.ok(a_rows[0]["pick_group"] != b_rows[0]["pick_group"], "a different expiry is a group of its own")
    c0.eq([r["lot_reference"] for r in a_rows], sorted(r["lot_reference"] for r in a_rows),
          "the lots of a group are listed oldest first")
    c0.eq(rows[-1]["batch_number"], "LOTB", "nearest expiry first: LOTB (later expiry) is last")
    # (3) quantity 12 fills the oldest lot of the group (10) then the next (2).
    c0.eq([D(r["fefo"]) for r in a_rows], [D(10), D(2)], "12 fills the oldest lot, then the next")
    # over-ask: the rest goes on the last lot, not dropped.
    s2, b2 = picker(api, p, 100)
    r2 = data(b2) if s2 == 200 else []
    # The case says the rest of an over-ask lands on the last lot "so the line shows red".
    # The API caps the split at what the lots hold (25) and leaves the overflow to the
    # screen; the screen half is not driven here (see the round file).
    c0.eq(sum(D(r["fefo"]) for r in r2), D(25), "an over-ask of 100 is split only over what the lots hold (API half)")
# (4) the untracked product: no printed batch; a dash on screen = has_printed_batch False.
s, body = picker(api, q, 1)
qrows = data(body) if s == 200 else []
c0.eq(len(qrows), 1, "untracked product shows its lot")
if qrows:
    r = qrows[0]
    c0.eq(r["has_printed_batch"], False, "has_printed_batch is False so the screen shows a dash")
    c0.eq(r["received_on"], today().isoformat(), "the received date is sent")
    c0.ok(str(r["lot_reference"]).startswith("LOT-"), "the LOT reference is sent separately", r["lot_reference"])
# (5) a user without PRODUCT_VIEW_COST_PRICE: cost column gone, pick works.
store = client("store", "lots")
s, body = picker(store, p, 12)
c0.eq(s, 200, "the storeman reads the picker")
srows = data(body) if s == 200 else []
c0.ok(srows and all(r.get("unit_cost") is None for r in srows), "no unit_cost without the cost permission", srows[:1])
c0.ok(rows and all(r.get("unit_cost") is not None for r in rows), "the Firm admin sees unit_cost", rows[:1])
c0.done()
