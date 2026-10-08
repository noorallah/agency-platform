"""Probe: a shared field switched off twice, on twice; the audit trail of it."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from common import Check, client, data, message
from _lib import must

c = Check("q_switch_twice")
admin, platform = client("admin"), client("platform_in_test01")
BF = "/api/v1/business-framework"
CODE = "GTQ_TRADE_LICENCE_NO"
s, b = platform.get(f"{BF}/attribute-definitions?search={CODE}&page_size=10")
found = [r for r in data(b) if r["code"] == CODE]
shared = found[0] if found else must(platform.post(f"{BF}/attribute-definitions", {
    "code": CODE, "name": "Trade licence no (check)", "entity_type": "CUSTOMER",
    "data_type": "TEXT", "mandatory": False}), "shared field")
fid = shared["id"]


def rows() -> int:
    """How many use_changed rows this field has."""
    s, b = admin.get("/api/v1/audit-logs?action=firm_custom_field.use_changed&page_size=100")
    return len([r for r in data(b) if (r.get("after_data") or {}).get("code") == CODE])


admin.put(f"{BF}/firm-custom-fields/{fid}/use", {"is_enabled": True})
start = rows()
c.eq(admin.put(f"{BF}/firm-custom-fields/{fid}/use", {"is_enabled": False})[0], 200, "off")
c.eq(admin.put(f"{BF}/firm-custom-fields/{fid}/use", {"is_enabled": False})[0], 200, "off again is accepted")
c.eq(rows(), start + 1, "switching off twice writes one audit row")
c.eq(admin.put(f"{BF}/firm-custom-fields/{fid}/use", {"is_enabled": True})[0], 200, "on")
c.eq(admin.put(f"{BF}/firm-custom-fields/{fid}/use", {"is_enabled": True})[0], 200, "on again is accepted")
c.eq(rows(), start + 2, "switching on twice writes one more audit row")
c.refused(admin.put(f"{BF}/firm-custom-fields/00000000-0000-0000-0000-000000000099/use",
                    {"is_enabled": False}), 404, "not found", "an unknown field")
c.eq(admin.put(f"{BF}/firm-custom-fields/{fid}/use", {})[0], 422, "a body without is_enabled")
c.done()
