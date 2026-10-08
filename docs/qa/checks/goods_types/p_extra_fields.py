"""Probe: create-only and never-sent fields are refused where they must be."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _gt import *  # noqa: F401,F403

c = Check("p_extra_fields")
tag = suffix()
admin = client("admin")
med = ensure_use(admin, "MEDICINE")
strip10 = next(r for r in data(admin.get(SETS)[1]) if r["firm_id"] is None and r["name"] == "Strip, box of 10")
status, body = prod(admin, tag, "E1", goods_type_id=med["id"])
c.eq(status, 422, f"goods_type_id on create is not a field ({status} {message(body)})")
status, body = prod(admin, tag, "E2")
p = data(body)
put = {"code": p["code"], "name": p["name"], "product_type": "STOCK_ITEM"}
for field, value in (("goods_type_id", med["id"]), ("unit_set_id", strip10["id"]), ("unit_conversion_factor", "5")):
    status, body = admin.put(f"{PRODUCTS}/{p['id']}", {**put, field: value})
    c.eq(status, 422, f"{field} on PUT is refused ({status} {message(body)})")
back = get_product(admin, p["id"])
c.eq((back.get("goods_type_id"), back.get("unit_set_id")), (None, None), "nothing leaked in through the refused writes")
# A category's goods_type_id is a field of the category, but the type must be one the firm uses.
off = goods_type_by_code(admin, "COSMETICS")
if not off["in_use"]:
    c.refused(make_category(admin, tag, "OFF", goods_type_id=off["id"]), 422,
              "not among the goods types this firm uses", "a category carrying a type the firm does not use")
else:
    c.ok(True, "Cosmetics is in use just now; the not-in-use refusal is also covered through an own type")
status, body = admin.post(GT, {"code": f"{tag}-GONE", "name": f"Gone {tag}"})
gone = data(body)
admin.put(f"{GT}/{gone['id']}/use", {"in_use": False})
c.refused(make_category(admin, tag, "OFF2", goods_type_id=gone["id"]), 422,
          "not among the goods types this firm uses", "a category carrying an own type that is no longer in use")
c.refused(make_category(admin, tag, "BOGUS", goods_type_id="00000000-0000-0000-0000-000000000000"), 422,
          "unavailable", "a category carrying an unknown type")
admin.delete(f"{GT}/{gone['id']}")
c.done()
