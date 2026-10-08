"""Probe (round 10): an adjustment request through its whole life (STK-8).

What it is worth is judged when it is approved, a decision is taken once,
a refused approval leaves it waiting, and a request that could never be
posted is not accepted.
"""
import uuid

from _inv import *
from _flow import *

c = Check("p_request_lifecycle")
w = World()
store = client("store")
wh = w.warehouse()
p = w.product()
w.stock_in(wh["id"], p["id"], 200, 10)
LIM = f"{INV}/adjustment-limits"
REQ = f"{INV}/adjustment-requests"
base = {"branch_id": w.branch_id, "warehouse_id": wh["id"], "product_id": p["id"], "transaction_date": w.today}


def wo(qty: str, ref: str, **extra: str) -> dict:
    """A write-off request body."""
    return {"kind": "WRITE_OFF", "write_off": {**base, "quantity": qty, "reason": "DAMAGE", "reference_number": f"{ref}{w.tag}", **extra}}


def status_of(request_id: str) -> str:
    """Which list a request is in."""
    for name in ("PENDING", "APPROVED", "REJECTED"):
        st, b = w.admin.get(f"{REQ}?status={name}")
        if any(r["id"] == request_id for r in data(b)):
            return name
    return "NOWHERE"


try:
    st, b = w.admin.put(LIM, {"limits": [{"role_code": "INVENTORY_MANAGER", "max_value": "500"}]})
    c.eq(st, 200, "limit of 500 set for the warehouse role")

    # 1. worth 400 when asked, 4,000 when approved
    st, b = store.post(REQ, wo("40", "RA"))
    c.eq(st, 201, "a request for 40 pieces at 10 is accepted")
    first = data(b)
    c.eq(D(first["estimated_value"]), D(400), "it says 400")
    w.stock_in(w.warehouse("X")["id"], p["id"], 200, 190)  # the average is now 100
    answer = store.post(f"{REQ}/{first['id']}/approve", {})
    c.refused(answer, 422, "limit", "40 pieces are worth 4,000 now, over the requester's limit of 500")
    c.eq(w.qty(p["id"], wh["id"]), D(200), "the refused approval moved nothing")
    c.eq(status_of(first["id"]), "PENDING", "and the request still waits")

    # 2. one decision, once
    st, b = w.admin.post(f"{REQ}/{first['id']}/reject", {"reason": "   "})
    c.eq(st, 422, "a rejection of only spaces is refused")
    st, b = w.admin.post(f"{REQ}/{first['id']}/reject", {})
    c.eq(st, 422, "a rejection with no reason is refused")
    st, b = w.admin.post(f"{REQ}/{first['id']}/approve", {})
    c.eq(st, 200, "the administrator approves")
    c.eq(w.qty(p["id"], wh["id"]), D(160), "40 pieces left")
    if st == 200:
        c.ok(data(b)["transaction_id"], "the request names its movement", data(b))
    answer = w.admin.post(f"{REQ}/{first['id']}/approve", {})
    c.refused(answer, 422, "already approved", "a second approval is refused")
    answer = w.admin.post(f"{REQ}/{first['id']}/reject", {"reason": "changed my mind"})
    c.refused(answer, 422, "already approved", "an approved request cannot be rejected")
    c.eq(w.qty(p["id"], wh["id"]), D(160), "still 360")

    st, b = store.post(REQ, wo("3", "RB"))
    second = data(b)
    st, b = w.admin.post(f"{REQ}/{second['id']}/reject", {"reason": "not damaged"})
    c.eq(st, 200, "a request is rejected with a reason")
    c.eq(status_of(second["id"]), "REJECTED", "it is in the rejected list")
    answer = w.admin.post(f"{REQ}/{second['id']}/approve", {})
    c.refused(answer, 422, "already rejected", "a rejected request cannot be approved")
    c.eq(w.qty(p["id"], wh["id"]), D(160), "a rejected request moved nothing")

    # 3. more than is held: refused at approval, and it goes on waiting
    st, b = store.post(REQ, wo("5000", "RC"))
    if c.eq(st, 201, "a request for more than is held is accepted (stock may arrive)"):
        third = data(b)
        st, b = w.admin.post(f"{REQ}/{third['id']}/approve", {})
        c.eq(st, 422, "approving it is refused while the stock is not there")
        c.eq(w.qty(p["id"], wh["id"]), D(160), "nothing moved")
        c.eq(status_of(third["id"]), "PENDING", "the request still waits")
        w.admin.post(f"{REQ}/{third['id']}/reject", {"reason": "probe"})

    # 4. what could never be posted is not accepted
    ghost = str(uuid.uuid4())
    for label, change in (
        ("an unknown product", {"product_id": ghost}),
        ("an unknown warehouse", {"warehouse_id": ghost}),
        ("an unknown reason", {"reason": "NOSUCHREASON"}),
        ("an unknown unit", {"entered_uom_id": ghost}),
    ):
        body = wo("1", "RD")
        body["write_off"].update(change)
        st, b = store.post(REQ, body)
        c.ok(st in (404, 422), f"a request naming {label} is refused", (st, message(b)))
        if st == 201:
            w.admin.post(f"{REQ}/{data(b)['id']}/reject", {"reason": "probe"})
    st, b = store.post(REQ, {"kind": "ADJUSTMENT", "write_off": wo("1", "RE")["write_off"]})
    c.eq(st, 422, "a kind with the other body is refused")
    st, b = w.admin.get(f"{REQ}?status=NOPE")
    c.eq(st, 422, "an unknown status filter is refused")
    st, b = w.admin.post(f"{REQ}/{ghost}/approve", {})
    c.eq(st, 404, "an unknown request is not found")

    # 5. many at once: each on its own
    st, b = store.post(REQ, wo("2", "RF"))
    fine = data(b)
    st, b = w.admin.post(
        f"{REQ}/bulk-approve",
        {"items": [
            {"id": fine["id"], "version": fine["version"]},
            {"id": first["id"], "version": first["version"]},
            {"id": ghost, "version": 1},
        ]},
    )
    if c.eq(st, 200, "bulk approve answers"):
        rows = {r["id"]: r for r in data(b)["results"]}
        c.ok(rows[fine["id"]]["outcome"] == "DONE", "the waiting one is approved", rows[fine["id"]])
        c.ok(rows[first["id"]]["outcome"] == "REFUSED", "the decided one is refused", rows[first["id"]])
        c.ok(rows[ghost]["outcome"] == "REFUSED", "the unknown one is refused", rows[ghost])
        c.eq(w.qty(p["id"], wh["id"]), D(158), "only the two pieces left")
finally:
    w.admin.put(LIM, {"limits": []})
c.done()
