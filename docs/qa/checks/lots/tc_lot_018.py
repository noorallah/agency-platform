"""TC-LOT-018: above the MRP warns with tax, refused before tax (HTTP steps 1-3; no screen step)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _lot import *  # noqa: F401,F403

c0 = Check("tc_lot_018")
api = lot_admin(); c = Ctx(api); p = margin_product(api)
m2 = batch_of(c, p, "TEST03-M2")
warn = m2.get("mrp_warning") or ""
c0.ok("132.16" in warn and "110.16" in warn, "(1) TEST03-M2 carries the warning naming 132.16 and 110.16", warn)
g = c.receive([{"product": p, "qty": 10, "rate": 80, "mrp": 130, "retail_margin_percent": 40}])
ln = receipt_line(api, g)
c0.ok("132.16" in (ln.get("mrp_warning") or "") and "110.16" in (ln.get("mrp_warning") or ""),
      "(1) a receipt line over the MRP completes and carries the warning", ln.get("mrp_warning"))


def refused(extra: dict) -> tuple[int, object]:
    """Try a one-line receipt (draft) and return the raw answer."""
    order = must(api.post("/api/v1/purchases", {
        "branch_id": c.branch["id"], "warehouse_id": c.warehouse["id"], "vendor_id": c.vendor["id"],
        "purchase_date": today().isoformat(),
        "lines": [{"product_id": p["id"], "ordered_quantity": "10", "unit_price": "80",
                   "purchase_uom_id": c.piece["id"], "inventory_uom_id": c.piece["id"]}]}), "po")
    must(api.post(f"/api/v1/purchases/{order['id']}/submit", {}), "submit")
    must(api.post(f"/api/v1/purchases/{order['id']}/approve", {}), "approve")
    pl = must(api.get(f"/api/v1/purchases/{order['id']}"), "po read")["lines"][0]
    s, b = api.post("/api/v1/goods-receipts", {
        "purchase_order_id": order["id"], "receipt_date": today().isoformat(),
        "invoice_reference": f"R{suffix(8)}", "lines": [{
            "purchase_order_line_id": pl["id"], "line_number": 1, "current_receipt_quantity": "10",
            "unit_price": "80", "warehouse_id": c.warehouse["id"], **extra}]})
    if s == 201:  # the refusal may come only at completion
        s, b = api.post(f"/api/v1/goods-receipts/{data(b)['id']}/complete", {})
    return s, b


s, b = refused({"mrp": "100", "retail_margin_percent": "40"})
c0.ok(s in (400, 422) and "mrp" in message(b).lower(), "(2) a price above the MRP before tax is refused", (s, message(b)))
s, b = refused({"retail_margin_percent": "10", "wholesale_margin_percent": "40"})
c0.ok(s in (400, 422) and "PTS 112.00" in message(b) and "PTR 88.00" in message(b), "(3) wholesale above retail is refused naming PTS 112.00 and PTR 88.00", (s, message(b)))
c0.done()
