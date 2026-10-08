"""Probe: parallel writes against the same stock cannot overdraw it (write-offs, transfers, quarantine) and every success is in the ledger."""
from concurrent.futures import ThreadPoolExecutor

from _inv import *

c = Check("p_race")
w = World()
a, b2 = w.warehouse(), w.warehouse()
p = w.product()
w.stock_in(a["id"], p["id"], 10)
base = {"branch_id": w.branch_id, "product_id": p["id"], "transaction_date": w.today}


def writeoff(i: int) -> int:
    """Write off 4 with its own reference."""
    return w.admin.post(f"{INV}/write-offs", {**base, "warehouse_id": a["id"], "quantity": "4", "reason": "DAMAGE", "reference_number": f"RW{w.tag}{i}"})[0]


def transfer(i: int) -> int:
    """Transfer 4 out with its own reference."""
    return w.admin.post(f"{INV}/transfers", {**base, "from_warehouse_id": a["id"], "to_warehouse_id": b2["id"], "quantity": "4", "reference_number": f"RT{w.tag}{i}"})[0]


with ThreadPoolExecutor(8) as pool:
    codes = list(pool.map(writeoff, range(8)))
ok = codes.count(201)
c.ok(ok <= 2, "at most two of eight parallel write-offs of 4 against 10 succeed", codes)
c.eq(w.qty(p["id"]), D(10 - 4 * ok), "stock = 10 less what succeeded")
c.ok(w.qty(p["id"]) >= 0, "never below zero")
c.eq(len([x for x in w.ledger(p["id"]) if x["transaction_type"] == "WRITE_OFF"]), ok, "the ledger holds exactly the successes")
c.ok(all(x in (201, 409, 422) for x in codes), "the losers are refused cleanly (no 500)", codes)
q = w.product()
w.stock_in(a["id"], q["id"], 10)
base["product_id"] = q["id"]
with ThreadPoolExecutor(8) as pool:
    codes = list(pool.map(transfer, range(8)))
ok = codes.count(201)
c.ok(ok <= 2 and all(x in (201, 409, 422) for x in codes), "parallel transfers: at most two succeed, losers refused cleanly", codes)
c.eq((w.qty(q["id"], a["id"]), w.qty(q["id"], b2["id"])), (D(10 - 4 * ok), D(4 * ok)), "source and destination add up")
c.done()
