"""Probe (round 9): the adjustment limit judges what moves, not the number typed (D-STK-57).

A write-off or adjustment typed in a pack unit moves the pack's worth of
pieces, so 3 boxes of 12 at 60 a piece is 2,160 -- not 180.
"""
from _inv import *
from _flow import *

c = Check("p_limit_in_packs")
w = World()
store = client("store")
wh = w.warehouse()
p = w.product()
w.stock_in(wh["id"], p["id"], 200, 60)
LIM = f"{INV}/adjustment-limits"
REQ = f"{INV}/adjustment-requests"
box = next(u["id"] for u in all_rows(w.admin, "/api/v1/uom-framework/uoms") if u["code"] == "BOX")
must(
    w.admin.post(
        "/api/v1/uom-framework/conversion-rules",
        {"product_id": p["id"], "from_uom_id": box, "to_uom_id": w.piece, "conversion_factor": "12", "effective_from": w.today},
    ),
    "a box of 12",
)
base = {"branch_id": w.branch_id, "warehouse_id": wh["id"], "product_id": p["id"], "transaction_date": w.today}


def wo(qty: str, ref: str, **extra: str) -> dict:
    """A write-off body."""
    return {**base, "quantity": qty, "reason": "DAMAGE", "reference_number": f"{ref}{w.tag}", **extra}


def adj(qty: str, ref: str, **extra: str) -> dict:
    """An adjustment body."""
    return {**base, "quantity": qty, "reference_number": f"{ref}{w.tag}", **extra}


try:
    st, b = w.admin.put(LIM, {"limits": [{"role_code": "INVENTORY_MANAGER", "max_value": "500"}]})
    c.eq(st, 200, "limit of 500 set for the warehouse role")
    # 8 pieces = 480: within
    st, b = store.post(f"{INV}/write-offs", wo("8", "PC"))
    c.eq(st, 201, "8 pieces (480) is within the limit")
    c.eq(w.qty(p["id"]), D(192), "8 pieces left")
    # 3 boxes = 36 pieces = 2,160: over
    answer = store.post(f"{INV}/write-offs", wo("3", "BX", entered_uom_id=box))
    c.refused(answer, 422, "limit", "a write-off of 3 boxes (2,160) is over the limit of 500")
    c.eq(w.qty(p["id"]), D(192), "the refused boxes moved nothing")
    answer = store.post(f"{INV}/write-offs", wo("36", "BXE", entered_quantity="3", entered_uom_id=box))
    c.refused(answer, 422, "limit", "the same typed as entered_quantity 3 boxes is over the limit")
    c.eq(w.qty(p["id"]), D(192), "still nothing moved")
    # the adjustment, down and up
    answer = store.post(f"{INV}/adjustments", adj("-3", "AD", entered_uom_id=box))
    c.refused(answer, 422, "limit", "an adjustment of minus 3 boxes is over the limit")
    answer = store.post(f"{INV}/adjustments", adj("3", "AU", entered_uom_id=box))
    c.refused(answer, 422, "limit", "an adjustment of plus 3 boxes is over the limit")
    c.eq(w.qty(p["id"]), D(192), "no adjustment moved anything")
    # half a box = 6 pieces = 360 would be within, were a box divisible; one box = 720 is over
    answer = store.post(f"{INV}/write-offs", wo("1", "B1", entered_uom_id=box))
    c.refused(answer, 422, "limit", "one box (720) is over the limit")
    # a request in boxes states what it is worth
    st, b = store.post(REQ, {"kind": "WRITE_OFF", "write_off": wo("3", "RQ", entered_uom_id=box)})
    c.eq(st, 201, "a request for 3 boxes is accepted")
    if st == 201:
        row = data(b)
        c.eq(D(row["estimated_value"]), D(2160), "the request says 2,160")
        st, b = store.post(f"{REQ}/{row['id']}/approve", {})
        c.ok(st in (403, 422), "the requester cannot approve it (worth more than their limit)", (st, message(b)))
        c.eq(w.qty(p["id"]), D(192), "nothing moved by the refused approval")
        st, b = w.admin.post(f"{REQ}/{row['id']}/approve", {})
        c.eq(st, 200, "the administrator approves")
        c.eq(w.qty(p["id"]), D(192 - 36), "36 pieces left on approval")
finally:
    w.admin.put(LIM, {"limits": []})
c.done()
