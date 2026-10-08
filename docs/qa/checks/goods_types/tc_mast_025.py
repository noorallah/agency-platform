"""TC-MAST-025: a firm switches a shared extra field off, and its values are kept."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from common import Check, client, data, message, state, suffix
from _lib import customer_body, field, must

c = Check("tc_mast_025")
tag = suffix()
admin, manager, platform = client("admin"), client("manager"), client("platform_in_test01")
other = client("test02_admin")
firm = state()["firms"]["TEST01"]
base = "/api/v1/business-framework"
CODE = "GTQ_TRADE_LICENCE_NO"

# the shared field: one for every run (a shared catalogue row cannot be removed once used)
s, b = platform.get(f"{base}/attribute-definitions?search={CODE}&page_size=10")
found = [r for r in data(b) if r["code"] == CODE]
if found:
    shared = found[0]
else:
    shared = must(platform.post(f"{base}/attribute-definitions", {
        "code": CODE, "name": "Trade licence no (check)", "entity_type": "CUSTOMER",
        "data_type": "TEXT", "mandatory": False}), "shared field")
fid = shared["id"]
# start from "on" whatever an earlier run left
admin.put(f"{base}/firm-custom-fields/{fid}/use", {"is_enabled": True})


def trail() -> list[dict]:
    """The use_changed audit rows for this field in the firm, oldest first."""
    s, b = admin.get("/api/v1/audit-logs?action=firm_custom_field.use_changed&page_size=100")
    rows = [r for r in data(b) if (r.get("after_data") or {}).get("code") == CODE]
    return sorted(rows, key=lambda r: r["created_at"])


def offered(api, which=fid) -> bool:
    """Whether a customer form of this firm is offered the field."""
    s, b = api.get(f"{base}/attribute-definitions/applicable?entity_type=CUSTOMER")
    return which in [d["id"] for d in data(b)["definitions"]]


def enabled() -> object:
    """What the firm's list says about the field."""
    s, b = admin.get(f"{base}/firm-custom-fields")
    return next(r["enabled_for_firm"] for r in data(b) if r["id"] == fid)


held_before = len(trail())
c.ok(offered(admin), "precondition: the field is offered to the firm")

# (a)
a = admin.post("/api/v1/customers", customer_body(
    f"SF{tag}", attributes=[{"attribute_definition_id": fid, "value": "TL-77"}]))
c.eq(a[0], 201, "(a) a customer with a value in the shared field")
cust = data(a[1]) if a[0] == 201 else {"id": ""}

# (b)
b = admin.put(f"{base}/firm-custom-fields/{fid}/use", {"is_enabled": False})
c.eq(b[0], 200, "(b) switching the shared field off is accepted")
c.eq(enabled(), False, "(b) the list shows the field off for this firm")

# (c) the old customer still shows the value, a new form is not offered the field
s, bd = admin.get(f"/api/v1/customers/{cust['id']}")
c.eq([x.get("value_text") for x in data(bd).get("attributes", [])], ["TL-77"],
     "(c) the existing customer still shows its value")
c.ok(not offered(admin), "(c) a new customer form is not offered the field")

# (d)
d = admin.post("/api/v1/customers", customer_body(
    f"SG{tag}", attributes=[{"attribute_definition_id": fid, "value": "TL-1"}]))
c.refused(d, 422, "do not apply", "(d) a new customer carrying a value for the switched-off field")

# (e) the second firm
# (e) NOT DRIVEN: TEST01 and TEST02 are separate SCHEMA stores, so a shared field made
# in one is not in the other; a second firm in the same store would need a SHARED firm.
# CASE TEXT: (e) needs two firms of one store (two SHARED firms), which no fixture makes.

# (h) the manager, while it is off
h = manager.put(f"{base}/firm-custom-fields/{fid}/use", {"is_enabled": True})
c.eq(h[0], 403, "(h) the firm manager cannot switch it")
c.eq(enabled(), False, "(h) and it stayed off")

# (f)
f = admin.put(f"{base}/firm-custom-fields/{fid}/use", {"is_enabled": True})
c.eq(f[0], 200, "(f) switching it on again")
s, bd = admin.get(f"/api/v1/customers/{cust['id']}")
c.eq([x.get("value_text") for x in data(bd).get("attributes", [])], ["TL-77"],
     "(f) the value saved in (a) is there, unchanged")
c.ok(offered(admin), "(f) offered again")

# (g) one of the firm's own fields
own = field(admin, f"OWNSW_{tag}", "CUSTOMER")
g = admin.put(f"{base}/firm-custom-fields/{own['id']}/use", {"is_enabled": False})
c.refused(g, 404, "own", "(g) a firm's own field cannot be switched, it is made inactive")

# audit: off then on
new = trail()[held_before:]
c.eq([(r["after_data"]["is_enabled"]) for r in new], [False, True],
     "audit: two firm_custom_field.use_changed rows, off then on")
c.done()
