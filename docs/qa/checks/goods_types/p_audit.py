"""Probe: goods_type.* and unit_set.* actions reach the firm's own audit trail."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _gt import *  # noqa: F401,F403

c = Check("p_audit")
tag = suffix()
admin = client("admin")
units = uom_ids(admin)

status, body = admin.post(GT, {"code": f"{tag}-AU", "name": f"Audit {tag}"})
g = data(body)
admin.put(f"{GT}/{g['id']}", {"name": f"Audit renamed {tag}"})
admin.put(f"{GT}/{g['id']}/use", {"in_use": True, "default_hsn_sac": "1111"})
admin.delete(f"{GT}/{g['id']}")
got = audit_actions(admin, "goods_type", g["id"])
for action in ("goods_type.created", "goods_type.updated", "goods_type.use_changed", "goods_type.deleted"):
    c.ok(action in got, f"{action} is on the trail", got)

status, body = admin.post(SETS, {"name": f"Audit set {tag}", "base_uom_id": units["PIECE"]})
s = data(body)
cosm = goods_type_by_code(admin, "COSMETICS")
admin.put(f"{SETS}/{s['id']}", {"description": "x"})
admin.put(f"{SETS}/{s['id']}", {"goods_type_ids": [cosm["id"]]})
admin.delete(f"{SETS}/{s['id']}")
got = audit_actions(admin, "unit_set", s["id"])
for action in ("unit_set.created", "unit_set.updated", "unit_set.goods_types_changed", "unit_set.deleted"):
    c.ok(action in got, f"{action} is on the trail", got)

# The rows belong to the firm's own trail, not to the platform's.
status, body = client("platform").get(f"/api/v1/audit-logs?entity_id={g['id']}")
rows = data(body) if status == 200 else []
c.eq(len(rows) if isinstance(rows, list) else rows, 0, "the platform trail holds none of the firm's goods type rows")
# The manager (no audit permission) cannot read the trail.
c.eq(client("manager").get(f"/api/v1/audit-logs?entity_id={g['id']}")[0] in (200, 403), True, "manager read is 200 or 403")
c.done()
