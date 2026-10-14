"""TC-LOT-013: costs are hidden without PRODUCT_VIEW_COST_PRICE (the Viewer role), shown to the admin."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _lot import *  # noqa: F401,F403

c0 = Check("tc_lot_013")
api = lot_admin(); c = Ctx(api)
p = c.product("B"); q = c.product("P", batch=False, allow_negative_stock=True)
lots = two_lots(c, p, 10, 10)
inv = c.bill(c.sell([{"product": p, "qty": 2}])["note"])
c.receive([{"product": q, "qty": 1, "rate": 30}])
lot_settings(api, True)
try:
    nid = c.note([{"product": q, "qty": 3}])["note"]["id"]
    must(c.dispatch(nid, confirm=True), "dispatch without stock")     # 2 units wait for a cost
    viewer = client("viewer", "lots")
    PICK = "/api/v1/batch-serial/batches/availability"
    paths = {
        "lots": f"{INV}/reports/stock-valuation/lots?product_id={p['id']}",
        "margin": "/api/v1/sales-invoices/reports/margin-by-lot",
        "short": f"{INV}/lot-shortfalls",
        "picker": f"{PICK}?product_id={p['id']}&warehouse_id={c.warehouse['id']}&quantity=1",
        "trail": f"/api/v1/batch-serial/batches/{lots['a']['id']}/trail",
    }
    seen = {}
    for who, user in (("viewer", viewer), ("admin", api)):
        for key, path in paths.items():
            s, b = user.get(path)
            c0.eq(s, 200, f"{who} opens {key} (no failure)")
            seen[(who, key)] = data(b) if s == 200 else None

    def costs(key, payload):
        """Return the cost-bearing values of one answer."""
        if payload is None:
            return []
        if key == "lots":
            return [r.get("rate") for r in payload] + [r.get("value") for r in payload]
        if key == "margin":
            rows = [r for r in payload if r["product_id"] == p["id"]]
            return [r.get(k) for r in rows for k in ("cost", "margin", "margin_percent")]
        if key == "short":
            rows = [r for r in payload if r["product_id"] == q["id"]]
            return [r.get(k) for r in rows for k in ("unit_cost", "cost_waiting")]
        if key == "picker":
            return [r.get("unit_cost") for r in payload]
        return [payload.get("unit_cost")] + [e.get("cost_amount") for e in payload["events"]]

    for key in paths:
        v = costs(key, seen[("viewer", key)])
        c0.ok(all(x is None for x in v), f"{key}: every cost, value and margin is left out for the Viewer", v)
        a = costs(key, seen[("admin", key)])
        c0.ok(a and all(x is not None for x in a), f"{key}: the Firm admin sees them all", a)
    c0.ok(len([r for r in seen[("viewer", "short")] if r["product_id"] == q["id"]]) == 1, "the waiting bill is listed for the Viewer (quantities stay)")
    c0.ok(len([r for r in seen[("viewer", "lots")]]) == 2, "quantities and references stay on the lot report")
finally:
    lot_settings(api, False)
c0.done()
