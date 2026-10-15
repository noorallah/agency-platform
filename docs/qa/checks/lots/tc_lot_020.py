"""TC-LOT-020: the bill switch, Retail or Wholesale, from the customer's kind (HTTP; no screen step).

Steps 1-4 are read through GET /price-levels/unit-prices (what the document's lines start at)
and through a sales order saved with no unit price; step 5 renames Retail (and puts it back)
and tries to delete and to retire it.
"""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _lot import *  # noqa: F401,F403

c0 = Check("tc_lot_020")
api = lot_admin(); c = Ctx(api); p = margin_product(api)
levels = {r["code"]: r for r in rows_of(api.get("/api/v1/price-levels"))}
retail, whole = levels["RETAIL"], levels["WHOLESALE"]
lot_r = by_code(api, "/api/v1/customers", "LOT-R"); lot_w = by_code(api, "/api/v1/customers", "LOT-W")


def asked(customer: dict, level: dict | None = None) -> tuple[Decimal, str | None]:
    """Return the unit price and the level the server worked it at."""
    q = (f"/api/v1/price-levels/unit-prices?product_ids={p['id']}&on={today().isoformat()}"
         f"&customer_id={customer['id']}&branch_id={c.branch['id']}&warehouse_id={c.warehouse['id']}")
    if level:
        q += f"&price_level_id={level['id']}"
    got = must(api.get(q), "unit prices")
    return D(got["prices"][0]["unit_price"]), got["price_level_id"]


price, lvl = asked(lot_r)
c0.eq((price, lvl), (D("100.00"), retail["id"]), "(1) LOT-R reads Retail and 100.00 (first lot out)")
price, lvl = asked(lot_r, whole)
c0.eq((price, lvl), (D("90.00"), whole["id"]), "(2) switched to Wholesale: 90.00")
price, lvl = asked(lot_w)
c0.eq((price, lvl), (D("90.00"), whole["id"]), "(3) LOT-W reads Wholesale and 90.00")
price, lvl = asked(lot_w, retail)
c0.eq((price, lvl), (D("100.00"), retail["id"]), "(4) switched to Retail: 100.00")


def order_price(customer: dict, level: dict | None) -> Decimal:
    """Save an order line with no price and return the price it was given."""
    body = {"customer_id": customer["id"], "order_date": today().isoformat(),
            "warehouse_id": c.warehouse["id"], "branch_id": c.branch["id"],
            "lines": [{"line_number": 1, "product_id": p["id"], "quantity": "1"}]}
    if level:
        body["price_level_id"] = level["id"]
    order = must(api.post("/api/v1/sales-orders", body), "sales order")
    return D(order["lines"][0]["unit_price"])


c0.eq(order_price(lot_r, None), D("100.00"), "an order for LOT-R with no price is priced 100.00")
c0.eq(order_price(lot_r, whole), D("90.00"), "an order for LOT-R at Wholesale is priced 90.00")
c0.eq(order_price(lot_w, None), D("90.00"), "an order for LOT-W with no price is priced 90.00")
# (5) rename, then try to delete and to retire.
write = {"code": retail["code"], "name": f"Retail {c.tag}", "sort_order": retail["sort_order"], "is_active": True}
s, b = api.put(f"/api/v1/price-levels/{retail['id']}", write)
try:
    c0.eq(s, 200, f"(5) renaming Retail is accepted ({message(b)})")
    s2, b2 = api.delete(f"/api/v1/price-levels/{retail['id']}")
    c0.ok(s2 in (409, 422), "(5) deleting Retail is refused", (s2, message(b2)))
    s3, b3 = api.put(f"/api/v1/price-levels/{retail['id']}", {**write, "is_active": False})
    c0.ok(s3 in (409, 422), "(5) making Retail inactive is refused", (s3, message(b3)))
finally:
    api.put(f"/api/v1/price-levels/{retail['id']}", {**write, "name": retail["name"]})
c0.done()
