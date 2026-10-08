"""TC-MAST-021 (the part with an API): what GET /products/metadata returns for the product form."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _gt import *  # noqa: F401,F403

c = Check("tc_mast_021")
tag = suffix()
admin = client("admin")
med = ensure_use(admin, "MEDICINE", hsn="3004", group="GST_12_LOCAL")
elec = ensure_use(admin, "ELECTRONICS")
tablets = cat(admin, tag, "TABLETS", goods_type_id=med["id"])
phones = cat(admin, tag, "PHONES", goods_type_id=elec["id"])
sundries = cat(admin, tag, "SUNDRIES")
strips = cat(admin, tag, "STRIPS", parent_id=tablets["id"])


def meta(query=""):
    status, body = admin.get(f"{PRODUCTS}/metadata{query}")
    return status, (data(body) if status == 200 else body)


status, m0 = meta()
c.eq(status, 200, "metadata with no category")
c.eq(m0.get("goods_type_id"), None, "no category: goods_type_id is null (General)")
c.ok(m0.get("goods_types") and m0.get("unit_sets"), "goods_types and unit_sets are always present")

status, m = meta(f"?category_id={tablets['id']}")
c.eq(m.get("goods_type_id"), med["id"], "Tablets: Medicine")
opt = {o["code"]: o for o in m["goods_types"]}
c.eq(sorted(opt["MEDICINE"]["switches"]), sorted([
    "track_batch", "track_expiry", "track_manufacturing_date", "track_serial", "track_warranty",
    "require_batch_on_receipt", "require_batch_on_issue", "require_serial_on_receipt", "require_serial_on_issue"]),
     "Medicine lists its nine switches")
c.eq({k: v for k, v in opt["MEDICINE"]["switches"].items() if v},
     {"track_batch": True, "track_expiry": True, "track_manufacturing_date": True,
      "require_batch_on_receipt": True, "require_batch_on_issue": True}, "Medicine switches on")
c.eq({k for k, v in opt["ELECTRONICS"]["switches"].items() if v},
     {"track_serial", "track_warranty", "require_serial_on_receipt", "require_serial_on_issue"}, "Electronics switches on")
c.eq((opt["MEDICINE"]["default_hsn_sac"], opt["MEDICINE"]["default_tax_profile_group_code"]), ("3004", "GST_12_LOCAL"),
     "Medicine defaults ride in the metadata")

status, m = meta(f"?category_id={phones['id']}")
c.eq(m.get("goods_type_id"), elec["id"], "Phones: Electronics")
status, m = meta(f"?category_id={sundries['id']}")
c.eq(m.get("goods_type_id"), None, "Sundries: General")
status, m = meta(f"?category_id={strips['id']}")
c.eq(m.get("goods_type_id"), med["id"], "Strips (no type of its own) inherits Medicine")

# A default whose tax group the firm has since lost is not offered: drop the group's profiles is out of reach,
# so only the offered shape is asserted here.
c.ok(all(set(o) >= {"id", "code", "name", "switches", "default_hsn_sac", "default_tax_profile_group_code"}
         for o in m["goods_types"]), "each option has the documented shape")
c.ok(all({"id", "name", "base_uom_id", "conversion_factor", "goods_type_ids"} <= set(u) for u in m["unit_sets"]),
     "each unit set option has the documented shape")

# Every role that can open the product form reads the same metadata.
for who in ("manager", "sales", "store"):
    c.eq(client(who).get(f"{PRODUCTS}/metadata?category_id={tablets['id']}")[0], 200, f"{who} reads the metadata")
c.done()
