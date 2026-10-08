"""TC-STOCK-016: large adjustments need approval."""
from _inv import *
from _flow import *

c = Check("tc_stock_016")
w = World()
store = client("store")
wh = w.warehouse()
p = w.product()
w.stock_in(wh["id"], p["id"], 200, 60)
LIM = f"{INV}/adjustment-limits"
REQ = f"{INV}/adjustment-requests"
base = {"branch_id": w.branch_id, "warehouse_id": wh["id"], "product_id": p["id"], "transaction_date": w.today}


def wo(qty: str, ref: str) -> dict:
    """A write-off body."""
    return {**base, "quantity": qty, "reason": "DAMAGE", "reference_number": f"{ref}{w.tag}"}


try:
    st, b = w.admin.put(LIM, {"limits": [{"role_code": "INVENTORY_MANAGER", "max_value": "500"}]})
    c.eq(st, 200, "limit of 500 set for the warehouse role")
    # within the limit posts directly
    st, b = store.post(f"{INV}/write-offs", wo("5", "OK"))
    c.eq(st, 201, "300 at cost is within the limit")
    # worth 2,040 at cost: refused, naming the limit
    st, b = store.post(f"{INV}/write-offs", wo("34", "BIG"))
    c.refused((st, b), 422, "limit", "a write-off over the role limit is refused naming the limit")
    c.eq(w.qty(p["id"]), D(195), "nothing moved by the refusal")
    # submit for approval
    made = []
    for qty in ("34", "35", "36"):
        st, b = store.post(REQ, {"kind": "WRITE_OFF", "write_off": wo(qty, "REQ" + qty)})
        c.eq(st, 201, f"request for {qty} accepted")
        if st == 201:
            made.append(data(b))
    c.eq(w.qty(p["id"]), D(195), "a request moves no stock")
    if len(made) == 3:
        # the requester cannot approve their own
        st, b = store.post(f"{REQ}/{made[0]['id']}/approve", {})
        c.ok(st == 403 or st == 422, "the requester cannot approve (their own limit is lower)", (st, message(b)))
        # administrator approves the first: posts unchanged
        st, b = w.admin.post(f"{REQ}/{made[0]['id']}/approve", {})
        c.eq(st, 200, "administrator approves")
        c.eq(w.qty(p["id"]), D(195 - 34), "approval posts the write-off unchanged")
        # reject the second with a reason
        st, b = w.admin.post(f"{REQ}/{made[1]['id']}/reject", {"reason": "not damaged"})
        c.eq(st, 200, "reject with a reason")
        c.eq((data(b)["status"], data(b)["decision_remarks"]), ("REJECTED", "not damaged"), "the reason is kept")
        c.eq(w.qty(p["id"]), D(195 - 34), "reject moves nothing")
        st, b = w.admin.post(f"{REQ}/{made[1]['id']}/approve", {})
        c.ok(st in (409, 422), "a rejected request cannot then be approved", (st, message(b)))
        st, b = w.admin.post(f"{REQ}/{made[0]['id']}/approve", {})
        c.ok(st in (409, 422), "an approved request cannot be approved twice", (st, message(b)))
        c.eq(w.qty(p["id"]), D(195 - 34), "no double posting")
    # bulk approve two
    more = []
    for qty in ("40", "41"):
        st, b = store.post(REQ, {"kind": "WRITE_OFF", "write_off": wo(qty, "BLK" + qty)})
        more.append(data(b))
    st, b = w.admin.post(f"{REQ}/bulk-approve", {"items": [{"id": r["id"], "version": r.get("version")} for r in more]})
    c.eq(st, 200, "bulk approve")
    c.eq(w.qty(p["id"]), D(195 - 34 - 81), "both posted")
    # no limit -> as before
    st, b = w.admin.put(LIM, {"limits": []})
    c.eq(st, 200, "limits cleared")
    st, b = store.post(f"{INV}/write-offs", wo("34", "FREE"))
    c.eq(st, 201, "with no limit the big write-off posts directly again")
finally:
    w.admin.put(LIM, {"limits": []})
c.done()
