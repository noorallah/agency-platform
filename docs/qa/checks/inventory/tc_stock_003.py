"""TC-STOCK-003: write-off posts to the adjustment account; quarantine posts nothing."""
from _inv import *
from _flow import *

c = Check("tc_stock_003")
w = World()
w1 = w.warehouse()
p = w.product()
w.stock_in(w1["id"], p["id"], 50)
base = {"branch_id": w.branch_id, "warehouse_id": w1["id"], "product_id": p["id"],
        "transaction_date": w.today}
ref = f"WO-{w.tag}"
st, b = w.admin.post(f"{INV}/write-offs", {**base, "quantity": "1", "reason": "DAMAGE", "reference_number": ref})
c.ok(st in (200, 201), "write-off accepted", (st, message(b)))
c.eq(w.qty(p["id"]), D(49), "49 after the write-off")
led = w.ledger(p["id"])
c.ok(any(x["transaction_type"] == "WRITE_OFF" and D(x["quantity"]) == 1 and x["reference_number"] == ref for x in led),
     "ledger WRITE_OFF 1", [(x["transaction_type"], x["quantity"]) for x in led])
js = entries(w, ref)
c.eq(len(js), 1, "one journal for the write-off")
if js:
    net = by_purpose(w, js[0])
    c.eq(net.get("INVENTORY_ADJUSTMENT"), D(60), "Dr inventory adjustment 60")
    c.eq(net.get("INVENTORY"), D(-60), "Cr inventory 60")
# quarantine
qh, qr = f"QH-{w.tag}", f"QR-{w.tag}"
st, b = w.admin.post(f"{INV}/quarantine", {**base, "action": "HOLD", "quantity": "2", "reference_number": qh})
c.ok(st in (200, 201), "hold accepted", (st, message(b)))
row = w.rows(p["id"])[0]
c.eq((D(row["current_quantity"]), D(row["available_quantity"]), D(row["quarantine_quantity"])),
     (D(47), D(47), D(2)), "after hold: current 47, available 47, quarantine 2 (as the case notes)")
st, b = w.admin.post(f"{INV}/quarantine", {**base, "action": "RELEASE", "quantity": "2", "reference_number": qr})
c.ok(st in (200, 201), "release accepted", (st, message(b)))
row = w.rows(p["id"])[0]
c.eq((D(row["current_quantity"]), D(row["available_quantity"]), D(row["quarantine_quantity"])),
     (D(49), D(49), D(0)), "after release: back to 49")
types = [x["transaction_type"] for x in w.ledger(p["id"])]
c.ok("QUARANTINE_HOLD" in types and "QUARANTINE_RELEASE" in types, "hold and release in the ledger", types)
c.eq(len(entries(w, qh)) + len(entries(w, qr)), 0, "no journal for quarantine")
st, b = w.admin.post(f"{INV}/quarantine", {**base, "action": "HOLD", "quantity": "999", "reference_number": qh + "X"})
c.refused((st, b), 422 if st == 422 else 409, "999", "hold of 999 refused by name")
c.done()
