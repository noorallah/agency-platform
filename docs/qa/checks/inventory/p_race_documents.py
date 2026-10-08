"""Probe: the same document actioned in parallel acts once (opening-stock post, count post, transfer dispatch/receive, request approve, repack cancel)."""
from concurrent.futures import ThreadPoolExecutor

from _inv import *

c = Check("p_race_documents")
w = World()
a, b2 = w.warehouse(), w.warehouse()
p = w.product()
w.stock_in(a["id"], p["id"], 40, 60)
store = client("store")


def many(fn, n: int = 6) -> list[int]:  # noqa: ANN001
    """Run fn n times at once; return the statuses."""
    with ThreadPoolExecutor(n) as pool:
        return list(pool.map(lambda _i: fn(), range(n)))


# opening stock posted in parallel
q = w.product()
os_ = must(w.admin.post(f"{INV}/opening-stock", {"branch_id": w.branch_id, "warehouse_id": b2["id"], "reference_number": f"RO{w.tag}", "posting_date": w.today,
                                                "lines": [{"product_id": q["id"], "quantity": "7", "unit_cost": "5"}]}), "draft")
codes = many(lambda: w.admin.post(f"{INV}/opening-stock/{os_['id']}/post", {})[0])
c.eq(codes.count(200), 1, "an opening-stock batch posted six times at once posts once: " + str(codes))
c.eq(w.qty(q["id"]), D(7), "7 on hand, not 14 or 42")
# count posted in parallel
cnt = must(w.admin.post(f"{INV}/counts", {"branch_id": w.branch_id, "warehouse_id": a["id"], "count_date": w.today}), "count")
w.admin.put(f"{INV}/counts/{cnt['id']}", {"lines": [{"product_id": p["id"], "counted_quantity": "30"}]})
codes = many(lambda: w.admin.post(f"{INV}/counts/{cnt['id']}/post", {})[0])
c.eq(codes.count(200), 1, "a count posted six times at once posts once: " + str(codes))
c.eq(w.qty(p["id"], a["id"]), D(30), "30 on hand (one -10 adjustment)")
# transfer dispatch in parallel
t = must(w.admin.post(f"{INV}/stock-transfers", {"transfer_date": w.today, "from_warehouse_id": a["id"], "to_warehouse_id": b2["id"], "lines": [{"product_id": p["id"], "quantity": "10"}]}), "transfer")
codes = many(lambda: w.admin.post(f"{INV}/stock-transfers/{t['id']}/dispatch", {})[0])
c.eq(codes.count(200), 1, "a transfer dispatched six times at once leaves once: " + str(codes))
c.eq(w.qty(p["id"], a["id"]), D(20), "20 left at the source")
codes = many(lambda: w.admin.post(f"{INV}/stock-transfers/{t['id']}/receive", {"lines": [{"line_number": 1, "received_quantity": "10"}]})[0])
c.eq(codes.count(200), 1, "and received once: " + str(codes))
c.eq(w.qty(p["id"], b2["id"]), D(10), "10 at the destination")
# request approved in parallel
w.admin.put(f"{INV}/adjustment-limits", {"limits": [{"role_code": "INVENTORY_MANAGER", "max_value": "100"}]})
try:
    base = {"branch_id": w.branch_id, "warehouse_id": a["id"], "product_id": p["id"], "transaction_date": w.today}
    req = data(store.post(f"{INV}/adjustment-requests", {"kind": "WRITE_OFF", "write_off": {**base, "quantity": "5", "reason": "DAMAGE", "reference_number": f"RQ{w.tag}"}})[1])
    codes = many(lambda: w.admin.post(f"{INV}/adjustment-requests/{req['id']}/approve", {})[0])
    c.eq(codes.count(200), 1, "a request approved six times at once posts once: " + str(codes))
    c.eq(w.qty(p["id"], a["id"]), D(15), "15 left (one write-off of 5)")
finally:
    w.admin.put(f"{INV}/adjustment-limits", {"limits": []})
# repack cancelled in parallel
pack = w.product("PK")
r = must(w.admin.post(f"{INV}/repacks", {"repack_date": w.today, "branch_id": w.branch_id, "warehouse_id": a["id"], "wastage_percent": "1",
                                         "lines": [{"kind": "CONSUME", "product_id": p["id"], "quantity": "5"}, {"kind": "PRODUCE", "product_id": pack["id"], "quantity": "10"}]}), "repack")
codes = many(lambda: w.admin.post(f"{INV}/repacks/{r['id']}/cancel", {"reason": "x"})[0])
c.eq(codes.count(200), 1, "a repack cancelled six times at once cancels once: " + str(codes))
c.eq((w.qty(p["id"], a["id"]), w.qty(pack["id"])), (D(15), D(0)), "the consumed stock is back once and the packs are gone")
c.done()
