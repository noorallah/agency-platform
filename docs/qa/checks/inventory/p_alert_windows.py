"""Probe (round 5): near expiry on Home and on the batch card are one count at any window, and goods in transit (D-STK-47).

Three batches of one item: one 20 days from its date, one 45 days, one 45 days and held only in quarantine. At the
firm's window of 30 Home's alerts and the batch card each count one more; at 60 each counts three more, the
quarantined batch among them; the two figures are equal at both. The near-expiry rows come soonest first. A transfer
on its way adds one to *in transit* and its row reads the quantity; cancelled, the count is back. The firm's window
is put back at the end."""
from _inv import *
from _flow import *
from _r3 import iso

c = Check("p_alert_windows")
w = World()
SET = "/api/v1/batch-serial/sale-settings"
CARD = "/api/v1/batch-serial/batches/summary"
held = must(w.admin.get(SET), "settings")


def window(days: int) -> None:
    """Set the firm's near-expiry window, keeping the rest of its rules."""
    body = {k: v for k, v in held.items() if k != "is_configured"}
    body["near_expiry_days"] = days
    must(w.admin.put(SET, body), "settings")


def both() -> tuple[int, int, dict]:
    """(Home's near-expiry count, the batch card's, the alerts)."""
    a = must(w.admin.get(f"{INV}/alerts"), "alerts")
    return a["near_expiry"], must(w.admin.get(CARD), "batch card")["near_expiry"], a


try:
    window(30)
    home30, card30, _ = both()
    c.eq(home30, card30, "before, at 30 days: Home and the batch card count the same batches")
    window(60)
    home60, card60, _ = both()
    c.eq(home60, card60, "before, at 60 days: the same")

    wh = w.warehouse()
    p = w.product(goods_type="MEDICINE")
    for number, days in ((f"N20{w.tag}", 20), (f"N45{w.tag}", 45), (f"Q45{w.tag}", 45)):
        r = receive(w, wh["id"], p["id"], 4, batch=number, mfg=iso(w, -30), expiry=iso(w, days))
        c.eq(r.get("status", (0,))[0], 200, f"batch {number} received")
    q = next(r for r in w.rows(p["id"]) if r.get("batch_number") == f"Q45{w.tag}")
    st, b = w.admin.post(f"{INV}/quarantine", {"branch_id": w.branch_id, "warehouse_id": wh["id"], "product_id": p["id"],
                                               "batch_id": q["batch_id"], "action": "HOLD", "quantity": "4",
                                               "transaction_date": w.today})
    c.ok(st in (200, 201), "the third batch is held whole in quarantine", (st, message(b)[:160]))
    q = next(r for r in w.rows(p["id"]) if r.get("batch_number") == f"Q45{w.tag}")
    c.eq((D(q["current_quantity"]), D(q["quarantine_quantity"])), (D(0), D(4)), "nothing of it on the shelf, four held")

    home, card, a = both()
    c.eq((home - home60, card - card60), (3, 3), "at 60 days both count three more, the quarantined batch among them")
    near = [r["detail"][-10:] for r in a["rows"] if r["kind"] == "NEAR_EXPIRY"]
    c.eq(near, sorted(near), "the near-expiry rows come soonest first")
    c.eq(len(near), min(10, home), "ten rows at most, and as many as there are when fewer")
    window(30)
    home, card, a = both()
    c.eq((home - home30, card - card30), (1, 1), "at 30 days both count one more: only the batch 20 days away")
    window(0)
    home, card, _ = both()
    c.eq((home, card), (0, 0), "a window of no days counts nothing on either")
finally:
    window(held["near_expiry_days"])
c.eq(must(w.admin.get(SET), "settings")["near_expiry_days"], held["near_expiry_days"], "the firm's window is as it was")

# goods in transit
before = must(w.admin.get(f"{INV}/alerts"), "alerts")
a_wh, b_wh = w.warehouse("TA"), w.warehouse("TB")
t = w.product("TR")
w.stock_in(a_wh["id"], t["id"], 9, 60)
ST = f"{INV}/stock-transfers"
made = must(w.admin.post(ST, {"transfer_date": w.today, "from_warehouse_id": a_wh["id"], "to_warehouse_id": b_wh["id"],
                              "lines": [{"product_id": t["id"], "quantity": "7"}]}), "transfer")
c.eq(must(w.admin.get(f"{INV}/alerts"), "alerts")["in_transit"], before["in_transit"], "a draft transfer is not in transit")
c.eq(w.admin.post(f"{ST}/{made['id']}/dispatch", {})[0], 200, "dispatched")
after = must(w.admin.get(f"{INV}/alerts"), "alerts")
c.eq(after["in_transit"] - before["in_transit"], 1, "one more item in transit")
moving = [(r["product_code"], D(r["quantity"])) for r in after["rows"] if r["kind"] == "IN_TRANSIT"]
c.eq(len(moving), min(10, after["in_transit"]), "ten in-transit rows at most")
c.eq([q for _, q in moving], sorted((q for _, q in moving), reverse=True), "the most on its way first")
if (t["code"], D(7)) not in moving:
    c.ok(len(moving) == 10 and moving[-1][1] >= D(7), "not listed, so the ten listed all carry at least as much", moving[-1:])
st, b = w.admin.post(f"{ST}/{made['id']}/cancel", {"reason": "probe over"})
c.eq(st, 200, "the transfer is cancelled")
c.eq(must(w.admin.get(f"{INV}/alerts"), "alerts")["in_transit"], before["in_transit"], "and nothing of it is in transit")
c.done()
