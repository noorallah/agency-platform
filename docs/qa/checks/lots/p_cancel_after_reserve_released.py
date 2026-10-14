"""Probe: a receipt whose lot was only reserved and released (an order cancelled) can still be cancelled."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _lot import *  # noqa: F401,F403

c0 = Check("p_cancel_after_reserve_released")
api = lot_admin(); c = Ctx(api)
p = c.product("B")
g = c.receive([{"product": p, "qty": 6, "rate": 40, "batch": "LOTA", "expiry": today() + timedelta(days=200), "mrp": 150}])
order = must(api.post("/api/v1/sales-orders", {
    "customer_id": c.customer["id"], "order_date": today().isoformat(),
    "warehouse_id": c.warehouse["id"], "branch_id": c.branch["id"],
    "lines": [{"line_number": 1, "product_id": p["id"], "quantity": "2", "unit_price": "100"}]}), "order")
must(api.post(f"/api/v1/sales-orders/{order['id']}/approve", {}), "approve")
s, b = api.post(f"/api/v1/sales-orders/{order['id']}/cancel", {"reason": "check"})
c0.eq(s, 200, f"the order is cancelled ({message(b)[:100]})")
s, b = api.post(f"/api/v1/goods-receipts/{g['id']}/cancel", {"reason": "check"})
c0.eq(s, 200, f"the receipt can be cancelled: nothing was sold, only reserved and released ({message(b)[:200]})")
c0.done()
