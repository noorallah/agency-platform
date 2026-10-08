"""Probe: a soft-deleted category carries nothing; a soft-deleted product and a deleted type."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _gt import *  # noqa: F401,F403

c = Check("p_deleted_category")
tag = suffix()
admin = client("admin")
status, body = admin.post(GT, {"code": f"{tag}-DEL", "name": f"Del {tag}", "track_batch": True})
own = data(body)
doomed = cat(admin, tag, "DOOMED", goods_type_id=own["id"])
c.eq(admin.delete(f"{PRODUCTS}/categories/{doomed['id']}")[0], 204, "category deleted")
c.refused(prod(admin, tag, "D1", category_id=doomed["id"]), 422, "unavailable", "a product in a deleted category")
status, body = admin.get(f"{PRODUCTS}/metadata?category_id={doomed['id']}")
c.eq(status, 200, f"metadata for a deleted category does not fail ({status})")
if status == 200:
    c.eq(data(body).get("goods_type_id"), None, "a deleted category hands out no type")
live = cat(admin, tag, "LIVE", goods_type_id=own["id"])
status, body = prod(admin, tag, "D2", category_id=live["id"])
p = data(body)
c.eq(p.get("goods_type_id"), own["id"], "product takes the type")
c.eq(admin.delete(f"{PRODUCTS}/{p['id']}")[0], 204, "product soft-deleted")
c.eq(admin.delete(f"{PRODUCTS}/categories/{live['id']}")[0], 204, "second category deleted")
# A soft-deleted product still holds the type.
status, body = admin.delete(f"{GT}/{own['id']}")
c.eq(status, 409, f"a type a deleted product still holds is not deleted ({status} {message(body)})")
c.ok("deleted product" in message(body), "the refusal names the deleted product", message(body))
status, body = admin.post(f"{PRODUCTS}/{p['id']}/restore")
if c.eq(status, 200, f"the product is restored ({message(body)})"):
    held = get_product(admin, p["id"]).get("goods_type_id")
    listed = [r["id"] for r in data(admin.get(GT)[1])]
    c.ok(held == own["id"] and held in listed, "the restored product still finds its goods type", held)
c.done()
