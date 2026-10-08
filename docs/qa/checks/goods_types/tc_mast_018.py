"""TC-MAST-018: a category changes type, a product changes category, a type in use cannot go."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _gt import *  # noqa: F401,F403

c = Check("tc_mast_018")
tag = suffix()
admin = client("admin")
food_before = goods_type_by_code(admin, "FOOD")["in_use"]
med = ensure_use(admin, "MEDICINE")
food = ensure_use(admin, "FOOD")
paint = ensure_use(admin, "PAINT")

syrups = cat(admin, tag, "SYRUPS", goods_type_id=med["id"])
enamels = cat(admin, tag, "ENAMELS", goods_type_id=paint["id"])
status, body = prod(admin, tag, "P1", category_id=syrups["id"])
c.eq(status, 201, "first product created in Syrups")
p1 = data(body)
c.eq(p1.get("goods_type_id"), med["id"], "first product takes Medicine")

def category_put(row, **extra):
    return admin.put(f"{PRODUCTS}/categories/{row['id']}", {"code": row["code"], "name": row["name"], **extra})

# Rename only: the type stays.
status, body = admin.put(
    f"{PRODUCTS}/categories/{syrups['id']}", {"code": syrups["code"], "name": f"Syrups renamed {tag}"})
c.eq(status, 200, f"rename saved ({message(body)})")
c.eq(data(body).get("goods_type_id"), med["id"], "rename leaves the category's type alone")

# Change to Food.
status, body = admin.put(f"{PRODUCTS}/categories/{syrups['id']}",
                         {"code": syrups["code"], "name": f"Syrups renamed {tag}", "goods_type_id": food["id"]})
c.eq(status, 200, f"type change saved ({message(body)})")
c.eq(data(body).get("goods_type_id"), food["id"], "category now Food")
c.eq(get_product(admin, p1["id"]).get("goods_type_id"), med["id"], "product already filed keeps Medicine")
status, body = prod(admin, tag, "P2", category_id=syrups["id"])
c.eq(status, 201, "second product created")
p2 = data(body)
c.eq(p2.get("goods_type_id"), food["id"], "second product takes Food")

# Move P1 to Enamels, then clear its category.
put = {"code": p1["code"], "name": p1["name"], "product_type": "STOCK_ITEM"}
status, body = admin.put(f"{PRODUCTS}/{p1['id']}", {**put, "category_id": enamels["id"]})
c.eq(status, 200, f"move to Enamels ({message(body)})")
c.eq(get_product(admin, p1["id"]).get("goods_type_id"), paint["id"], "moved product takes Paint")
status, body = admin.put(f"{PRODUCTS}/{p1['id']}", {**put, "category_id": None})
c.eq(status, 200, f"clear category ({message(body)})")
c.eq(get_product(admin, p1["id"]).get("goods_type_id"), None, "cleared category makes it General (null)")

# Stop using Food while Syrups carries it.
c.refused(admin.put(f"{GT}/{food['id']}/use", {"in_use": False}), 409,
          "is still the goods type of category", "stop using Food while a category carries it")
status, body = admin.put(f"{PRODUCTS}/categories/{syrups['id']}",
                         {"code": syrups["code"], "name": f"Syrups renamed {tag}", "goods_type_id": None})
c.eq(status, 200, "Syrups given General")
c.eq(data(body).get("goods_type_id"), None, "Syrups reads General")
status, body = admin.put(f"{GT}/{food['id']}/use", {"in_use": False})
c.eq(status, 200, f"stop using Food accepted once no category carries it ({message(body)})")
c.eq(get_product(admin, p2["id"]).get("goods_type_id"), food["id"], "product holding Food keeps it")

# The firm's own type: category then product then delete.
status, body = admin.post(GT, {"code": f"{tag}-OWN", "name": f"Own {tag}", "track_batch": True})
c.eq(status, 201, "own type created")
own = data(body)
ocat = cat(admin, tag, "OWNCAT", goods_type_id=own["id"])
status, body = prod(admin, tag, "P3", category_id=ocat["id"])
p3 = data(body)
c.eq(p3.get("goods_type_id"), own["id"], "product takes the own type")
c.refused(admin.delete(f"{GT}/{own['id']}"), 409, "is still the goods type of category", "delete while a category carries it")
status, body = admin.put(f"{PRODUCTS}/categories/{ocat['id']}", {"code": ocat["code"], "name": ocat["name"], "goods_type_id": None})
c.eq(status, 200, "category type cleared")
c.refused(admin.delete(f"{GT}/{own['id']}"), 409, "is still the goods type of product", "delete while a product holds it")
c.refused(admin.delete(f"{GT}/{own['id']}"), 409, "Deactivate it instead", "refusal says deactivate")

# Restore Food as found.
if food_before:
    ensure_use(admin, "FOOD")
c.done()
