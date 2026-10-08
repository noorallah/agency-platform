"""Probe: a field rule naming a goods type, group or field the firm cannot use."""
import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from common import Check, client, data, message, suffix
from _lib import field, goods_types, must, rule

c = Check("q_rule_targets")
tag = suffix()
admin, other = client("admin"), client("test02_admin")
BF = "/api/v1/business-framework"
shade = field(admin, f"QSHADE_{tag}", "PRODUCT")
creg = field(admin, f"QCREG_{tag}", "CUSTOMER")
types = goods_types(admin)

# another firm's field / goods type / group (separate stores here, so the ids are unknown to TEST01)
theirs = field(other, f"QTHEIR_{tag}", "PRODUCT")
c.refused(rule(admin, theirs["id"], category_code=f"TAB{tag}", is_mandatory=False), 422,
          "not one this firm can use", "a rule for a field of another firm")
own_type = must(other.post("/api/v1/products/goods-types", {"code": f"QT{tag}", "name": f"Q {tag}"}), "type")
c.refused(rule(admin, shade["id"], goods_type_id=own_type["id"], is_mandatory=False), 422,
          "not one this rule can name", "a rule naming another firm's goods type")
group = must(other.post("/api/v1/customers/groups", {"code": f"QG{tag}", "name": f"G {tag}"}), "group")
c.refused(rule(admin, creg["id"], customer_group_id=group["id"], is_mandatory=False), 422,
          "not this firm's", "a rule naming another firm's customer group")
c.refused(rule(admin, shade["id"], goods_type_id="00000000-0000-0000-0000-000000000099"), 422,
          "not one this rule can name", "a rule naming a goods type that does not exist")
c.refused(rule(admin, shade["id"]), 422, "exactly one", "a rule naming nothing")
c.refused(rule(admin, shade["id"], goods_type_id=types["PAINT"]["id"], category_code="X1"), 422,
          "exactly one", "a rule naming two things")

# a goods type the firm does not use: the catalogue's COSMETICS (not in use on TEST01)
cos = types["COSMETICS"]
if cos["in_use"]:
    c.ok(False, "precondition: COSMETICS should not be in use on TEST01")
else:
    r = rule(admin, shade["id"], goods_type_id=cos["id"], is_mandatory=False)
    # OBSERVATION: the code accepts any visible type, in use or not. A rule on an unused type is
    # inert until the firm uses it; the check records that this is what happens.
    c.eq(r[0], 201, "a rule naming a shared goods type the firm does not use is accepted (inert)")
    if r[0] == 201:
        admin.delete(f"{BF}/firm-custom-field-rules/{data(r[1])['id']}")
c.refused(admin.delete(f"{BF}/firm-custom-field-rules/00000000-0000-0000-0000-000000000099"), 404,
          "not found", "deleting a rule that does not exist")
c.done()
