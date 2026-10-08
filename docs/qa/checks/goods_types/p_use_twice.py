"""Probe: use and stop-use twice; defaults left alone, cleared, blank; a retired type."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _gt import *  # noqa: F401,F403

c = Check("p_use_twice")
tag = suffix()
admin = client("admin")
status, body = admin.post(GT, {"code": f"{tag}-OWN", "name": f"Own {tag}", "default_hsn_sac": "1234",
                               "default_tax_profile_group_code": "GST_5_LOCAL"})
own = data(body)
use = f"{GT}/{own['id']}/use"
c.eq(admin.put(use, {"in_use": False})[0], 200, "stop using an own type with no category")
status, body = admin.put(use, {"in_use": False})
c.eq(status, 200, f"stop using twice is harmless ({message(body)})")
c.eq(data(body)["in_use"], False, "still not in use")
c.eq((data(body)["default_hsn_sac"], data(body)["default_tax_profile_group_code"]), (None, None), "not in use reads no defaults")
status, body = admin.put(use, {"in_use": True, "default_hsn_sac": "4321"})
c.eq(status, 200, "use again with an HSN")
c.eq(data(body)["default_hsn_sac"], "4321", "HSN set")
status, body = admin.put(use, {"in_use": True})
c.eq(status, 200, "use twice is harmless")
c.eq(data(body)["default_hsn_sac"], "4321", "a default left out is left alone")
status, body = admin.put(use, {"in_use": True, "default_hsn_sac": None})
c.eq(data(body)["default_hsn_sac"], None, "an explicit null clears the default")
status, body = admin.put(use, {"in_use": True, "default_hsn_sac": "9999", "default_tax_profile_group_code": "   "})
c.eq((data(body)["default_hsn_sac"], data(body)["default_tax_profile_group_code"]), ("9999", None), "a blank box clears the tax group")
c.refused(admin.put(use, {"in_use": True, "default_hsn_sac": "X" * 21}), 422, "", "an HSN of 21 characters")
c.refused(admin.put(use, {}), 422, "", "use with no in_use")
c.refused(admin.put(use, {"in_use": True, "colour": "red"}), 422, "", "an unknown field")
# Retired: deactivate the type; it can neither be taken into use nor offered to a new category.
status, body = admin.put(f"{GT}/{own['id']}", {"is_active": False})
c.eq(status, 200, f"retire the type ({message(body)})")
c.refused(admin.put(use, {"in_use": True}), 422, "retired", "using a retired type")
c.refused(make_category(admin, tag, "RET", goods_type_id=own["id"]),
          422, "", "a category cannot carry a retired type")
c.eq(admin.put(f"{GT}/00000000-0000-0000-0000-000000000000/use", {"in_use": True})[0], 404, "an unknown id is 404")
admin.delete(f"{GT}/{own['id']}")
c.done()
