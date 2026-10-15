"""TC-LOT-015: a goods type hands its margins to a new product (HTTP steps 1-4; no screen step)."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _lot import *  # noqa: F401,F403

c0 = Check("tc_lot_015")
api = lot_admin(); c = Ctx(api)
units = c.piece["id"]
gt = must(api.post("/api/v1/products/goods-types", {
    "code": f"GM{c.tag}", "name": f"Margin type {c.tag}", "track_batch": True,
    "retail_margin_percent": "25", "wholesale_margin_percent": "12.5"}), "goods type")
cat = must(api.post("/api/v1/products/categories", {
    "code": f"GC{c.tag}", "name": f"Margin category {c.tag}", "goods_type_id": gt["id"]}), "category")


def make(name: str, **extra: object) -> tuple[int, object]:
    """Post a product of the goods type."""
    return api.post("/api/v1/products", {
        "code": f"P{name}{c.tag}", "name": f"GT item {name} {c.tag}", "brand_id": check_brand(api),
        "product_type": "STOCK_ITEM", "tax_profile_group_code": "GST_18_LOCAL",
        "selling_price": "100", "purchase_price": "50", "base_uom_id": units,
        "inventory_uom_id": units, "sales_uom_id": units, "purchase_uom_id": units,
        "category_id": cat["id"], "track_batch": True, **extra})


s, b = make("A"); c0.eq(s, 201, f"(1) product created ({message(b)})"); a = data(b)
if s != 201:
    c0.done()
c0.eq((D(a.get("retail_margin_percent")), D(a.get("wholesale_margin_percent"))), (D(25), D("12.5")),
      "(1) the product holds 25 and 12.5")
s, b = make("B", retail_margin_percent="30"); c0.eq(s, 201, f"(2) created ({message(b)})"); pb = data(b)
c0.eq((D(pb.get("retail_margin_percent")), D(pb.get("wholesale_margin_percent"))), (D(30), D("12.5")),
      "(2) retail 30, wholesale follows the type")
s, b = api.put(f"/api/v1/products/goods-types/{gt['id']}", {
    "retail_margin_percent": "20", "wholesale_margin_percent": "10"})
c0.eq(s, 200, f"(3) the type changed ({message(b)})")
now = must(api.get(f"/api/v1/products/{a['id']}"), "product read")
c0.eq((D(now.get("retail_margin_percent")), D(now.get("wholesale_margin_percent"))), (D(25), D("12.5")),
      "(3) the first product still holds 25 and 12.5")
for value in ("-1", "1000"):
    s, b = make(f"X{value.replace('-', 'M')}", retail_margin_percent=value)
    c0.ok(s == 422 and "retail_margin_percent" in message(b),
          f"(4) a margin of {value} is refused naming the field", (s, message(b)))
c0.done()
