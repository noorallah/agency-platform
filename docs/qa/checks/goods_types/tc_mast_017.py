"""TC-MAST-017: a goods type, a category that carries it, a product that takes it."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _gt import *  # noqa: F401,F403

c = Check("tc_mast_017")
tag = suffix()
admin = client("admin")

shared = shared_types(admin)
c.eq(sorted(shared), ["COSMETICS", "ELECTRONICS", "FOOD", "MEDICINE", "PAINT"], "five shared types")
c.ok(all(r["firm_id"] is None for r in shared.values()), "shared rows carry no firm")
med = shared["MEDICINE"]
c.ok(med["track_batch"] and med["track_expiry"], "Medicine tracks batch and expiry", med)

# A shared row cannot be changed or deleted; the refusal names it.
c.refused(admin.put(f"{GT}/{med['id']}", {"name": "Meds"}), 422,
          "is a shared goods type and cannot be changed here", "PUT on a shared type")
c.refused(admin.delete(f"{GT}/{med['id']}"), 422,
          "is a shared goods type and cannot be changed here", "DELETE on a shared type")

# Use Medicine, set defaults.
used = ensure_use(admin, "MEDICINE", hsn="3004", group="GST_12_LOCAL")
c.eq(used["in_use"], True, "Medicine in use")
c.eq((used["default_hsn_sac"], used["default_tax_profile_group_code"]), ("3004", "GST_12_LOCAL"), "defaults saved")
# A default tax group the firm does not have is refused.
c.refused(admin.put(f"{GT}/{med['id']}/use", {"in_use": True, "default_tax_profile_group_code": "NOSUCH_GROUP"}),
          422, "No active tax profile", "unknown default tax group on use")

# The firm's own type.
status, body = admin.post(GT, {"code": f"{tag}-SEED", "name": f"Seeds {tag}", "track_batch": True, "track_expiry": True})
c.eq(status, 201, "own type saved")
own = data(body) if status == 201 else {}
c.eq(own.get("in_use"), True, "own type in use at once")
c.eq(own.get("firm_id"), firm_ids()["TEST01"], "own type carries the firm")
c.refused(admin.post(GT, {"code": "MEDICINE", "name": "Another"}), 409, "already exists", "duplicate code MEDICINE")
c.refused(admin.post(GT, {"code": "medicine", "name": "Another"}), 409, "already exists", "duplicate code, lower case")
c.refused(admin.post(GT, {"code": f"{tag}-BAD", "name": "Bad", "default_tax_profile_group_code": "NOSUCH_GROUP"}),
          422, "No active tax profile", "unknown default tax group on create")

# Categories.
tablets = cat(admin, tag, "TABLETS", goods_type_id=med["id"])
c.eq(tablets.get("goods_type_id"), med["id"], "Tablets carries Medicine")
sundries = cat(admin, tag, "SUNDRIES")
c.eq(sundries.get("goods_type_id"), None, "Sundries carries none (General)")
strips = cat(admin, tag, "STRIPS", parent_id=tablets["id"])
c.eq(strips.get("goods_type_id"), None, "Strips has no type of its own")

# Products.
def made(name: str, **kw):
    status, body = prod(admin, tag, name, **kw)
    c.eq(status, 201, f"product {name} created ({message(body)})")
    return data(body) if status == 201 else {}

p_tab = made("P-TAB", category_id=tablets["id"])
p_strip = made("P-STRIP", category_id=tablets["id"], sub_category_id=strips["id"])
p_sun = made("P-SUN", category_id=sundries["id"])
p_none = made("P-NONE")
for label, row, expected in (("Tablets", p_tab, med["id"]), ("Tablets>Strips", p_strip, med["id"]),
                             ("Sundries", p_sun, None), ("no category", p_none, None)):
    if row:
        back = get_product(admin, row["id"])
        c.eq(back.get("goods_type_id"), expected, f"{label} product goods_type_id on read-back")
c.done()
