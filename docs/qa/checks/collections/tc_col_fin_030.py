"""TC-FIN-030: bills handed to a collector and taken back change no balance and no report."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _col import *

c = Check("tc_col_fin_030")
a = admin()
cashier = admin("cashier")
c1, c2 = collector_ids()
sc = Scene(a)
area_a, area_b = f"Alpha{sc.tag}", f"Beta{sc.tag}"
cu1 = sc.customer(addresses=address(area_a))
cu2 = sc.customer(addresses=address(area_b))
with counter(a):
    b11, b12 = sc.bill(cu1), sc.bill(cu1)  # 118.00 each
    b21, b22 = sc.bill(cu2), sc.bill(cu2)
mine = {b["id"] for b in (b11, b12, b21, b22)}


def rows() -> dict[str, dict]:
    """Return the handover-screen rows of the four bills, by invoice id."""
    got = all_rows(a, f"{COL}/handovers/bills?customer_id={cu1['id']}", 50)
    got += all_rows(a, f"{COL}/handovers/bills?customer_id={cu2['id']}", 50)
    return {r["invoice_id"]: r for r in got if r["invoice_id"] in mine}


def history() -> dict[str, dict]:
    """Return the handover history rows of the four bills, by invoice id."""
    return {r["invoice_id"]: r for r in all_rows(a, f"{COL}/handovers", 50) if r["invoice_id"] in mine}


def snapshot() -> tuple:
    """Return what a hand-over must not move: a customer's closing balance and the books."""
    return closing(a, cu1), position(a, cu1), trial_totals(a)


# 1, 2
start = snapshot()
listed = rows()
c.eq(len(listed), 4, "step 2: every unpaid bill is listed")
c.ok(all(r["collector_id"] is None for r in listed.values()), "with nobody holding it")
c.ok(all(area_a in r["customer_place"] or area_b in r["customer_place"] for r in listed.values()), "and the customer's area beside the name")
# 3
st, body = hand(a, [b11["id"]], c1)
c.eq(st, 201, "step 3: handed over")
c.eq((data(body)["bills"], D(data(body)["amount"])), (1, D("118.00")), "1 bill for 118.00")
row = rows()[b11["id"]]
c.eq((row["collector_id"], row["handed_on"]), (c1, today().isoformat()), "the row shows his id and today")
# 4
st, body = hand(a, [b11["id"], b12["id"]], c2)
c.eq(st, 409, "step 4: handing an out bill to the second collector is refused")
c.ok(b11["invoice_number"] in message(body), "naming the bill already out", message(body))
now = rows()
c.eq(now[b12["id"]]["collector_id"], None, "the other ticked bill stays in the office")
c.eq(now[b11["id"]]["collector_id"], c1, "and the first stays with the first collector")
# 5
st, body = a.post(f"{COL}/handovers", {"collector_id": c2, "handed_on": today().isoformat(), "matching": {"area": area_a.lower()}})
c.eq(st, 201, "step 5: hand over all matching the first area")
c.eq((data(body)["bills"], data(body)["already_out"]), (1, 1), "1 bill handed and 1 already out and left")
now = rows()
c.eq(now[b11["id"]]["collector_id"], c1, "the first bill is still with the first collector")
c.eq(now[b12["id"]]["collector_id"], c2, "the second is now with the second")
# 6
st, body = a.post(f"{COL}/handovers", {"collector_id": c2, "handed_on": today().isoformat(), "matching": {"number_from": b21["invoice_number"], "number_to": b21["invoice_number"]}})
c.eq(st, 201, "step 6: a one-number range")
now = rows()
c.eq(now[b21["id"]]["collector_id"], c2, "that bill goes out")
c.eq(now[b22["id"]]["collector_id"], None, "its neighbour does not")
# 7
c.eq(snapshot(), start, "step 7: the closing balance, position and the trial balance are what they were")
# 8
st, body = receipt(a, cu2, "118.00", [(b21, "118.00")])
c.eq(st, 201, "step 8: a receipt in full for a bill that is out")
c.ok(b21["id"] not in rows(), "it is no longer among the unpaid bills")
hist = history()
c.eq(hist[b21["id"]]["state"], "OUT", "History lists it as still out")
c.eq(D(hist[b21["id"]]["outstanding"]), D("0"), "owing 0.00 now")
c.eq(D(hist[b21["id"]]["outstanding_at_handover"]), D("118.00"), "with what it owed when handed")
after_receipt = snapshot()
# 9
out = [h["id"] for h in history().values() if h["state"] == "OUT"]
c.eq(len(out), 3, "three handovers are still out")
st, body = a.post(f"{COL}/handovers/take-back", {"handover_ids": out, "note": "check"})
c.eq(st, 200, "step 9: taking them back")
hist = history()
c.ok(all(h["state"] == "RETURNED" and h["returned_at"] for h in hist.values()), "every row reads as taken back with its date")
now = rows()
c.ok(all(r["collector_id"] is None for r in now.values()), "the unpaid bills show nobody under With")
c.eq(snapshot(), after_receipt, "the taking back moved no balance")
# 10
c.eq(cashier.get(f"{COL}/handovers/bills")[0], 200, "step 10: the Cashier sees the list")
c.eq(hand(cashier, [b22["id"]], c1)[0], 403, "but cannot hand a bill over")
c.eq(cashier.post(f"{COL}/handovers/take-back", {"handover_ids": out})[0], 403, "or take one back")
c.done()
