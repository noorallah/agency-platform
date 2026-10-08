"""Probe: goods_type.use_changed audit rows, and the refusals of the use endpoint."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from common import Check, client, data, message, state, suffix
from _lib import audit_actions

c = Check("q_goods_type_use_audit")
tag = suffix()
admin = client("generic_admin")
other = client("test02_admin")
generic = state()["own_firms"]["generic"]["id"]
GT = "/api/v1/products/goods-types"
s, b = admin.get(GT)
food = next(r for r in data(b) if r["code"] == "FOOD")
if food["in_use"]:
    admin.put(f"{GT}/{food['id']}/use", {"in_use": False})


def rows() -> list[dict]:
    """The use_changed rows for FOOD, oldest first."""
    found = [r for r in audit_actions(admin, generic, "goods_type.use_changed")
             if (r.get("after_data") or {}).get("code") == "FOOD"]
    return sorted(found, key=lambda r: r["created_at"])


start = len(rows())
c.eq(admin.put(f"{GT}/{food['id']}/use", {"in_use": True, "default_hsn_sac": "2106"})[0], 200, "use Food with an HSN")
c.eq(admin.put(f"{GT}/{food['id']}/use", {"in_use": False})[0], 200, "drop Food")
new = rows()[start:]
c.eq([r["after_data"].get("in_use") for r in new], [True, False], "two audit rows, in then out")
c.eq(new[0]["after_data"].get("default_hsn_sac") if new else None, "2106", "the first records the default HSN")
# refusals
c.refused(admin.put(f"{GT}/{food['id']}/use", {"in_use": True, "default_tax_profile_group_code": "NO_SUCH_GROUP"}),
          422, "", "a default tax group the firm does not have")
c.refused(admin.put(f"{GT}/00000000-0000-0000-0000-000000000099/use", {"in_use": True}), 404,
          "not found", "a goods type that does not exist")
theirs = data(other.post(GT, {"code": f"QO{tag}", "name": f"Other {tag}"})[1])
c.refused(admin.put(f"{GT}/{theirs['id']}/use", {"in_use": True}), 404, "not found",
          "using another firm's own goods type")
c.eq(admin.put(f"{GT}/{food['id']}/use", {})[0], 422, "a body without in_use")
s, b = admin.get(GT)
c.eq(next(r for r in data(b) if r["code"] == "FOOD")["in_use"], False, "Food ended not in use")
c.done()
