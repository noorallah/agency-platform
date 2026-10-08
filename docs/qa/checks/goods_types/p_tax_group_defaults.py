"""Probe: a default tax group the firm lacks is refused on create, update and use."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _gt import *  # noqa: F401,F403

c = Check("p_tax_group_defaults")
tag = suffix()
admin = client("admin")
status, body = admin.post(GT, {"code": f"{tag}-TG", "name": f"Tax {tag}", "default_tax_profile_group_code": "GST_12_LOCAL"})
c.eq(status, 201, f"a group the firm has is accepted ({message(body)})")
own = data(body)
c.eq(own["default_tax_profile_group_code"], "GST_12_LOCAL", "default saved")
c.refused(admin.put(f"{GT}/{own['id']}", {"default_tax_profile_group_code": "NOPE"}), 422, "No active tax profile", "update with a missing group")
c.refused(admin.put(f"{GT}/{own['id']}/use", {"in_use": True, "default_tax_profile_group_code": "NOPE"}), 422,
          "No active tax profile", "use with a missing group")
back = goods_type_by_code(admin, f"{tag}-TG")
c.eq(back["default_tax_profile_group_code"], "GST_12_LOCAL", "the refused writes changed nothing")
# lower case group codes: the product schema upper-cases HSN but demands upper-case groups
c.refused(admin.put(f"{GT}/{own['id']}", {"default_tax_profile_group_code": "gst_5_local"}), 422, "No active tax profile",
          "a lower-case group code does not match")
status, body = admin.put(f"{GT}/{own['id']}", {"default_tax_profile_group_code": None})
c.eq(status, 200, "an explicit null clears the group on update")
c.eq(data(body)["default_tax_profile_group_code"], None, "cleared")
admin.delete(f"{GT}/{own['id']}")
c.done()
