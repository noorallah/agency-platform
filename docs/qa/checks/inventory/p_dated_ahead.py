"""Probe (round 11): no stock write is dated after today (D-STK-66).

Stock moves when a movement is saved. One dated tomorrow, inside an open
period, was accepted by every stock write; the goods moved today, the
journal was dated tomorrow, and the trial balance disagreed with the
valuation until then. Today is still accepted, and nothing moves on a
refusal.
"""
from datetime import date, timedelta

from _inv import *
from _flow import *

c = Check("p_dated_ahead")
w = World()
store = client("store")
wh = w.warehouse()
other = w.warehouse("O")
p = w.product()
w.stock_in(wh["id"], p["id"], 20, 10)
tomorrow = (date.fromisoformat(w.today) + timedelta(days=1)).isoformat()


def bodies(on: str, tag: str) -> list[tuple[str, str, dict]]:
    """Each stock write, dated ``on``."""
    base = {"branch_id": w.branch_id, "warehouse_id": wh["id"], "product_id": p["id"], "transaction_date": on}
    write_off = {**base, "quantity": "1", "reason": "DAMAGE", "reference_number": f"WO{tag}{w.tag}"}
    return [
        ("a write-off", f"{INV}/write-offs", write_off),
        ("an adjustment", f"{INV}/adjustments", {**base, "quantity": "1", "reference_number": f"AD{tag}{w.tag}"}),
        ("a request for approval", f"{INV}/adjustment-requests", {"kind": "WRITE_OFF", "write_off": {**write_off, "reference_number": f"RQ{tag}{w.tag}"}}),
        ("a transfer", f"{INV}/transfers", {"branch_id": w.branch_id, "from_warehouse_id": wh["id"], "to_warehouse_id": other["id"], "product_id": p["id"], "quantity": "1", "transaction_date": on}),
        ("a count sheet", f"{INV}/counts", {"branch_id": w.branch_id, "warehouse_id": wh["id"], "count_date": on}),
        ("opening stock", f"{INV}/opening-stock", {"branch_id": w.branch_id, "warehouse_id": other["id"], "reference_number": f"OS-{w.tag}-{tag}", "posting_date": on, "lines": [{"product_id": p["id"], "quantity": "1", "unit_cost": "10"}]}),
    ]


for label, path, body in bodies(tomorrow, "T"):
    answer = store.post(path, body)
    c.refused(answer, 422, "after today", f"{label} dated tomorrow is refused")
    if answer[0] in (200, 201) and "counts" in path:
        w.admin.post(f"{path}/{data(answer[1])['id']}/cancel", {})
c.eq(w.qty(p["id"]), D(20), "nothing moved")

# a plan's sheet, and a draft moved ahead
st, b = w.admin.post(f"{INV}/count-plans", {"name": f"Ahead {w.tag}", "branch_id": w.branch_id, "warehouse_id": wh["id"], "frequency_days": 7})
plan = data(b)
answer = w.admin.post(f"{INV}/count-plans/{plan['id']}/sheet?count_date={tomorrow}", {})
c.refused(answer, 422, "after today", "a plan's sheet dated tomorrow is refused")
w.admin.delete(f"{INV}/count-plans/{plan['id']}")
st, b = w.admin.post(f"{INV}/opening-stock", {"branch_id": w.branch_id, "warehouse_id": other["id"], "reference_number": f"OS-{w.tag}-D", "posting_date": w.today, "lines": [{"product_id": p["id"], "quantity": "1", "unit_cost": "10"}]})
c.eq(st, 201, "an opening-stock draft dated today is saved")
draft = data(b)
answer = w.admin.put(f"{INV}/opening-stock/{draft['id']}", {"branch_id": w.branch_id, "warehouse_id": other["id"], "reference_number": draft["reference_number"], "posting_date": tomorrow, "lines": [{"product_id": p["id"], "quantity": "1", "unit_cost": "10"}]})
c.refused(answer, 422, "after today", "the draft cannot be moved to tomorrow")
st, b = w.admin.get(f"{INV}/opening-stock/{draft['id']}")
c.eq(data(b)["posting_date"], w.today, "it is still dated today")
w.admin.delete(f"{INV}/opening-stock/{draft['id']}")

# today is still today
for label, path, body in bodies(w.today, "N")[:5]:
    st, b = store.post(path, body)
    c.ok(st in (200, 201), f"{label} dated today is accepted", (st, message(b)))
    if st in (200, 201) and "counts" in path:
        w.admin.post(f"{path}/{data(b)['id']}/cancel", {})
    if st == 201 and "requests" in path:
        w.admin.post(f"{path}/{data(b)['id']}/reject", {"reason": "probe"})
c.eq(w.qty(p["id"]), D(20), "one written off, one added, one moved between warehouses: 20 are held")
c.done()
