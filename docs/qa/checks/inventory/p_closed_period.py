"""Probe (round 3): a stock write that posts to the books is refused in a closed month and moves nothing.

Closes the first month of the year and opens it again.
"""
from _r3 import *

c = Check("p_closed_period")
w = World()
wh = w.warehouse()["id"]
p = w.product()["id"]
w.stock_in(wh, p, 10)
PERIODS = "/api/v1/finance/accounting-periods"
periods = sorted((x for x in data(w.admin.get(f"{PERIODS}?page_size=50")[1]) if x["ends_on"] < w.today), key=lambda x: x["starts_on"])
if not periods:
    raise SystemExit("PRECONDITION: the firm has no month before this one to close")
first = periods[0]
st, body = w.admin.call("PATCH", f"{PERIODS}/{first['id']}", {"status": "CLOSED"})
if st != 200:
    raise SystemExit(f"PRECONDITION close {first['code']}: {st} {message(body)}")
try:
    on = first["ends_on"]
    base = {"branch_id": w.branch_id, "product_id": p, "transaction_date": on, "warehouse_id": wh}
    c.refused(w.admin.post(f"{INV}/write-offs", {**base, "quantity": "1", "reason": "DAMAGE", "reference_number": f"CW{w.tag}"}),
              422, "period", "a write-off dated in the closed month")
    c.refused(w.admin.post(f"{INV}/adjustments", {**base, "quantity": "-1", "reference_number": f"CA{w.tag}"}),
              422, "period", "an adjustment dated in the closed month")
    other = w.product()["id"]
    st, body = w.admin.post(f"{INV}/opening-stock", {"branch_id": w.branch_id, "warehouse_id": wh, "reference_number": f"CO-{w.tag}",
                                                      "posting_date": on, "lines": [{"product_id": other, "quantity": "1", "unit_cost": "5"}]})
    c.eq(st, 201, "a draft of opening stock may be dated in the closed month: " + message(body))
    if st == 201:
        c.refused(w.admin.post(f"{INV}/opening-stock/{data(body)['id']}/post", {}), 422, "period", "posting opening stock dated in the closed month")
    c.eq((w.qty(p, wh), w.qty(other, wh)), (D(10), D(0)), "no stock moved")
finally:
    st, body = w.admin.call("PATCH", f"{PERIODS}/{first['id']}", {"status": "OPEN"})
    c.eq(st, 200, f"{first['code']} is opened again: " + message(body))
c.done()
